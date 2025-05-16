# github_api.py
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

import requests
from datetime import datetime
import time
import itertools

# --- API keys ---
GITHUB_TOKEN_1 = os.getenv("GITHUB_TOKEN_1")
GITHUB_TOKEN_2 = os.getenv("GITHUB_TOKEN_2")
SERP_API_KEY = os.getenv("SERP_API_KEY", "")

GITHUB_TOKENS = [token for token in [GITHUB_TOKEN_1, GITHUB_TOKEN_2] if token]
token_pool = itertools.cycle(GITHUB_TOKENS)

# GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"  # Gemini API key removed
# GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent" # Gemini URL removed

# --- Helper functions ---

def get_headers():
    token = next(token_pool)
    return {"Authorization": f"token {token}"}

def safe_get(url):
    while True:
        headers = get_headers()
        try:
            response = requests.get(url, headers=headers)
        except requests.RequestException as e:
            print(f"GitHub API request failed: {e}")
            return {"error": "GitHub API request failed. Please check your network or token."}

        if response.status_code == 403:
            if "X-RateLimit-Remaining" in response.headers and response.headers["X-RateLimit-Remaining"] == "0":
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait_time = reset_time - int(time.time()) + 1
                print(f"GitHub rate limit hit. Sleeping for {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                print(f"403 Forbidden: {response.text}")
                return {"error": "GitHub API access forbidden. Check token or permissions."}
        elif response.status_code == 401:
            print("Unauthorized: Invalid GitHub token")
            return {"error": "Unauthorized access to GitHub API. Invalid token."}
        elif response.status_code == 200:
            return response
        else:
            print(f"GitHub API HTTP {response.status_code} Error: {response.text}")
            return {"error": f"GitHub API error {response.status_code}: {response.text}"}


# def get_gemini_synonyms(keyword): # Gemini function removed
#     genai.configure(api_key=GEMINI_API_KEY)
#     model = genai.GenerativeModel('gemini-1.5-pro-latest')
#     prompt = f"What are some technical synonyms and closely related terms for '{keyword}' in the context of software development and technology?"
#     try:
#         response = model.generate_content(prompt)
#         if response.text:
#             synonyms = [term.strip() for term in response.text.split(',') if term.strip()]
#             return synonyms
#         else:
#             print(f"Gemini API returned an empty response for '{keyword}'.")
#             return []
#     except Exception as e:
#         print(f"Error calling Gemini API for synonyms of '{keyword}': {e}")
#         return []

# def test_gemini_api(): # Gemini test function removed
#     try:
#         genai.configure(api_key=GEMINI_API_KEY)
#         model = genai.GenerativeModel('gemini-1.5-pro-latest')
#         response = model.generate_content("Hello")
#         if response and response.text:
#             print("Gemini API key is valid and working.")
#             return True
#         else:
#             print("Gemini API test failed: No response text.")
#             return False
#     except Exception as e:
#         print(f"Gemini API test failed: {e}")
#         return False

def calculate_experience_years(created_at):
    try:
        created_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
        years = (datetime.utcnow() - created_date).days // 365
        return years
    except Exception:
        return 0

def compute_confidence(years, repo_count, keyword_matches):
    base = min(100, years * 6 + repo_count * 2 + keyword_matches * 5)
    return round(min(base, 100))

def generate_variants(term):
    base = term.lower().replace(" ", "")
    variants = list(set([
        term,
        term.lower(),
        term.upper(),
        term.title(),
        term.replace(" ", ""),
        base,
        base.upper(),
        base.title()
    ]))
    if "machine" in term.lower():
        variants += ["ml", "ML", "Ml"]
    return variants

def search_linkedin_profile(name, location=None):
    query = f"{name} site:linkedin.com/in/"
    if location:
        query += f" {location}"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY
    }
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
        if response.status_code != 200:
            print(f"SerpAPI Error {response.status_code}: {response.text}")
            return None
        data = response.json()
        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if "linkedin.com/in/" in link:
                return link
    except requests.RequestException as e:
        print(f"SerpAPI request failed: {e}")
    return None

def search_github_users(domain, keywords=""):
    # if not test_gemini_api(): # Gemini test removed
    #     return {"error": "Gemini API key is invalid or not working."}

    keyword_list = [kw.strip().lower() for kw in keywords.split(",") if kw.strip()]
    domain_variants = generate_variants(domain)
    # gemini_synonyms = get_gemini_synonyms(domain) # Gemini synonym call removed
    # domain_variants.extend(gemini_synonyms) # Gemini synonyms extension removed
    domain_variants = list(set(domain_variants)) # Remove duplicates

    all_users = {}

    for variant in domain_variants:
        query = f"{variant} in:bio"
        url = f"https://api.github.com/search/users?q={query}&per_page=30"
        response = safe_get(url)
        if isinstance(response, dict) and "error" in response:
            return {"error": response["error"]}
        if not response:
            continue

        users = response.json().get("items", [])

        for user in users:
            username = user["login"]
            if username in all_users:
                continue

            profile_url = user["html_url"]
            user_resp = safe_get(f"https://api.github.com/users/{username}")
            if isinstance(user_resp, dict) and "error" in user_resp:
                continue
            if not user_resp:
                continue
            user_data = user_resp.json()
            if user_data.get("type") != "User":
                continue

            repos_resp = safe_get(f"https://api.github.com/users/{username}/repos")
            if isinstance(repos_resp, dict) and "error" in repos_resp:
                continue
            if not repos_resp:
                continue
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
                    repo_desc = (repo.get("description") or "").lower()
                    if kw in repo_desc:
                        keyword_match_count += 1

            confidence = compute_confidence(years, len(repos), keyword_match_count)
            explanation = f"{years} years on GitHub, {len(repos)} public repos, {keyword_match_count} keyword matches"

            linkedin_url = search_linkedin_profile(name, location)

            all_users[username] = {
                "name": name,
                "contact": profile_url,
                "linkedin": linkedin_url or "Not found",
                "location": location,
                "experience_years": years,
                "confidence_score": confidence,
                "explanation": explanation
            }

            time.sleep(1)

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
