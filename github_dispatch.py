"""Shared helper for dispatching the .github/workflows/scrape.yml GitHub
Actions job from Streamlit Cloud, where a real Chromium can't launch
in-process (see scraper.py's docstring). Used by both app.py's Refresh
button and the Admin page's Run Now button - one code path, like
collector.run_once() is for the in-process scrape.
"""
import requests
import streamlit as st

import config


def github_token():
    """GITHUB_TOKEN set in Streamlit Cloud's app secrets - its presence is
    what selects GitHub Actions dispatch over the in-process scrape.
    Absent locally, so local dev keeps using the fast in-process path.
    """
    try:
        return st.secrets["GITHUB_TOKEN"]
    except (KeyError, FileNotFoundError):
        return None


def trigger_github_scrape():
    token = github_token()
    url = (f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/"
           f"workflows/{config.GITHUB_WORKFLOW_FILE}/dispatches")
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"ref": "main"},
        timeout=15,
    )
    if resp.status_code == 204:
        return True, "Scrape job triggered on GitHub Actions."
    return False, f"GitHub API error {resp.status_code}: {resp.text}"
