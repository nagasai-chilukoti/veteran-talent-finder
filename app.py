import streamlit as st
import pandas as pd
from github_api import search_github_users

st.set_page_config(page_title="Veteran Talent Finder", layout="wide")
st.title("🧠 Veteran Talent Finder")

st.markdown("Enter a domain (e.g., `Cybersecurity`, `Machine Learning`) and optional keywords.")

# Input fields
domain = st.text_input("Domain", placeholder="e.g., Cybersecurity")
keywords = st.text_input("Optional Keywords", placeholder="e.g., Python, Cloud, AI")

# Initialize session state
if "results" not in st.session_state:
    st.session_state.results = None

if st.button("🔍 Find Experts"):
    if domain.strip() == "":
        st.warning("Please enter a domain.")
    else:
        with st.spinner("Searching GitHub for experienced professionals..."):
            results = search_github_users(domain, keywords)
            if results and not results.get("error"):
                st.session_state.results = results
            else:
                st.session_state.results = {"error": "No profiles found or GitHub API limit hit."}

# Proceed only if results exist
if st.session_state.results and not st.session_state.results.get("error"):
    results = st.session_state.results

    st.subheader("🔎 Filter Results")

    group_option = st.selectbox(
        "Select group to view:",
        ("✅ Experts with 10+ Years Experience",
         "💡 <10 Years but High Confidence",
         "📋 All Candidates"),
        index=0
    )

    group_map = {
        "✅ Experts with 10+ Years Experience": results.get("10_years_plus", []),
        "💡 <10 Years but High Confidence": results.get("strong_but_less_than_10", []),
        "📋 All Candidates": results.get("all_candidates", [])
    }

    selected_group = group_map[group_option]

    if not selected_group:
        st.info("No candidates found for the selected group.")
    else:
        df = pd.DataFrame(selected_group)

        # Location filter
        locations = sorted(df["location"].dropna().unique())
        location_filter = st.selectbox("🌍 Filter by Location", ["All"] + locations)
        if location_filter != "All":
            df = df[df["location"] == location_filter]

        # Confidence filter
        confidence_min = st.slider("🎯 Minimum Confidence Score", 0, 100, 60)
        df = df[df["confidence_score"] >= confidence_min]

        # Keyword re-filter
        keyword_refilter = st.text_input("🔁 Re-filter by keyword (optional)", "")
        if keyword_refilter.strip():
            df = df[df["explanation"].str.contains(keyword_refilter.strip(), case=False)]

        # View mode selector
        view_mode = st.selectbox("📊 Select View Format", ["Table", "Grid"])

        # Pagination
        page_size = 5
        total_pages = (len(df) - 1) // page_size + 1 if len(df) > 0 else 1
        page = st.number_input("📄 Page", min_value=1, max_value=total_pages, value=1)
        paginated_df = df.iloc[(page - 1) * page_size: page * page_size]

        if view_mode == "Table":
            st.dataframe(
                paginated_df[["name", "location", "contact", "experience_years", "confidence_score", "explanation"]],
                use_container_width=True
            )
        else:
            st.markdown("### 👥 Grid View")
            for i in range(0, len(paginated_df), 2):
                cols = st.columns(2)
                for j in range(2):
                    if i + j < len(paginated_df):
                        person = paginated_df.iloc[i + j]
                        with cols[j]:
                            st.markdown(f"#### 👤 {person.get('name') or 'N/A'}")
                            contact = person.get("contact") or "#"
                            st.markdown(f"🔗 [GitHub Profile]({contact})")
                            st.markdown(f"📍 Location: {person.get('location') or 'N/A'}")
                            st.markdown(f"💼 Experience: {person.get('experience_years') or 'N/A'} years")
                            st.markdown(f"🎯 Confidence Score: **{person.get('confidence_score', 0)}%**")
                            st.markdown(f"🧠 Why this score? {person.get('explanation') or 'N/A'}")
                            st.markdown("---")

        # Download button
        csv = df.to_csv(index=False)
        st.download_button("📥 Download Full CSV", data=csv, file_name="veteran_talent_results.csv", mime="text/csv")

elif st.session_state.results and st.session_state.results.get("error"):
    st.error(st.session_state.results.get("error"))
