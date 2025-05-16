from dotenv import load_dotenv
import os
import requests
from datetime import datetime
import time
import itertools
import concurrent.futures

try:
    import streamlit as st
    GITHUB_TOKEN_1 = st.secrets.get("GITHUB_TOKEN_1", None)
    GITHUB_TOKEN_2 = st.secrets.get("GITHUB_TOKEN_2", None)
    SERP_API_KEY = st.secrets.get("SERP_API_KEY", "")
except ImportError:
    GITHUB_TOKEN_1 = os.getenv("GITHUB_TOKEN_1")
    GITHUB_TOKEN_2 = os.getenv("GITHUB_TOKEN_2")
    SERP_API_KEY = os.getenv("SERP_API_KEY", "")

GITHUB_TOKENS = [token for token in [GITHUB_TOKEN_1, GITHUB_TOKEN_2] if token]
if not GITHUB_TOKENS:
    raise RuntimeError("No GitHub tokens found! Set them in environment or Streamlit secrets.")

token_pool = itertools.cycle(GITHUB_TOKENS)

def get_headers():
    token = next(token_pool)
    return {"Authorization": f"token {token}"}

def safe_get(url):
    headers = get_headers()
    try:
        response = requests.get(url, headers=headers)
    except requests.RequestException as e:
        print(f"GitHub API request failed: {e}")
        return None

    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
        wait_time = reset_time - int(time.time()) + 1
        print(f"GitHub rate limit hit. Sleeping for {wait_time} seconds...")
        time.sleep(wait_time)
        return safe_get(url)
    elif response.status_code == 200:
        return response
    else:
        print(f"GitHub API Error {response.status_code}: {response.text}")
        return None

def calculate_experience_years(created_at):
    try:
        created_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - created_date).days // 365
    except Exception:
        return 0

def compute_confidence(years, repo_count, keyword_matches):
    base = min(100, years * 6 + repo_count * 2 + keyword_matches * 5)
    return round(min(base, 100))

def generate_variants(term):
    base = term.lower().replace(" ", "")
    variants = list(set([
        term, term.lower(), term.upper(), term.title(), term.replace(" ", ""), base,
        base.upper(), base.title()
    ]))
    if "machine" in term.lower():
        variants += ["ml", "ML", "Ml"]
    return variants

def process_user(user, keyword_list):
    username = user["login"]
    profile_url = user["html_url"]
    user_resp = safe_get(f"https://api.github.com/users/{username}")
    if not user_resp:
        return None
    user_data = user_resp.json()
    if user_data.get("type") != "User":
        return None

    repos_resp = safe_get(f"https://api.github.com/users/{username}/repos")
    if not repos_resp:
        return None
    repos = repos_resp.json()

    years = calculate_experience_years(user_data.get("created_at", "2020-01-01T00:00:00Z"))
    location = user_data.get("location", "Unknown")
    name = user_data.get("name") or username

    keyword_match_count = 0
    bio = (user_data.get("bio") or "").lower()
    for kw in keyword_list:
        if kw in bio:
            keyword_match_count += 1
        for repo in repos:
            desc = (repo.get("description") or "").lower()
            if kw in desc:
                keyword_match_count += 1

    confidence = compute_confidence(years, len(repos), keyword_match_count)
    explanation = f"{years} years on GitHub, {len(repos)} public repos, {keyword_match_count} keyword matches"

    return {
        "name": name,
        "contact": profile_url,
        "linkedin": "Optional or Skipped",
        "location": location,
        "experience_years": years,
        "confidence_score": confidence,
        "explanation": explanation
    }

# 🔁 Modified: Accept multiple domain-keyword combos
def search_github_users(domain, keywords="", max_users=50):
    keyword_list = [kw.strip().lower() for kw in keywords.split(",") if kw.strip()]
    domain_variants = generate_variants(domain)
    all_users = {}

    for variant in domain_variants:
        for page in range(1, 4):  # Fetch up to 3 pages
            query = f"{variant} in:bio"
            url = f"https://api.github.com/search/users?q={query}&per_page=30&page={page}"
            response = safe_get(url)
            if not response:
                continue

            users = response.json().get("items", [])
            print(f"[DEBUG] Variant '{variant}' Page {page}: Found {len(users)} users")

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(process_user, user, keyword_list) for user in users]
                for future in concurrent.futures.as_completed(futures):
                    user_result = future.result()
                    if user_result and user_result["name"] not in all_users:
                        all_users[user_result["name"]] = user_result

            # If we already have enough users, break early
            if len(all_users) >= max_users:
                break
        if len(all_users) >= max_users:
            break

    results = list(all_users.values())
    group1 = sorted([r for r in results if r["experience_years"] >= 10], key=lambda x: -x["confidence_score"])
    group2 = sorted([r for r in results if r["experience_years"] < 10 and r["confidence_score"] >= 70], key=lambda x: -x["confidence_score"])
    group3 = sorted(results, key=lambda x: -x["confidence_score"])

    if not results:
        return {"error": "No profiles found. GitHub API may have returned no data or rate limits were reached."}

    return {
        "10_years_plus": group1,
        "strong_but_less_than_10": group2,
        "all_candidates": group3
    }

