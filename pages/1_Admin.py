"""Admin / data-management page: manual Run Now trigger, retrieval log, and
historical backfill import from CSV/Excel.
"""
import pandas as pd
import requests
import streamlit as st

import collector
import config
import data_utils


def _fmt_ts(iso_ts: str) -> str:
    return pd.to_datetime(iso_ts).strftime("%d-%b-%Y %H:%M")


def _github_token():
    """GITHUB_TOKEN set in Streamlit Cloud's app secrets - its presence is
    what selects GitHub Actions dispatch over the in-process scrape below,
    since a real Chromium can't launch on Streamlit Cloud (see scraper.py).
    Absent locally, so local dev keeps using the fast in-process path.
    """
    try:
        return st.secrets["GITHUB_TOKEN"]
    except (KeyError, FileNotFoundError):
        return None


def _trigger_github_scrape():
    token = _github_token()
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


st.set_page_config(page_title="Diesel Price - Admin", page_icon="🛠", layout="wide")
st.title("Admin / Data Management")

data_utils.init_db()

st.subheader("Manual scrape")
github_token = _github_token()
if github_token:
    st.caption(
        "Running on Streamlit Cloud: this triggers the `scrape.yml` GitHub Actions job "
        "(it runs the real scraper on a Chromium-capable runner and pushes the updated "
        "database). Streamlit Cloud auto-redeploys on that push, so the new price "
        "typically appears here within a few minutes - refresh this page after a bit."
    )
    if st.button("▶ Run Now"):
        with st.spinner("Triggering GitHub Actions..."):
            ok, message = _trigger_github_scrape()
        if ok:
            st.success(message)
            st.markdown(f"[View run status](https://github.com/{config.GITHUB_REPO}/actions)")
        else:
            st.error(message)
else:
    if st.button("▶ Run Now"):
        with st.spinner("Contacting MEDCO..."):
            result = collector.run_once()
        if result.success:
            st.success(f"[{result.status}] business_date={result.business_date} "
                       f"inserted={result.inserted_fuel_types} duplicate={result.duplicate_fuel_types}")
        else:
            st.error(f"[{result.status}] business_date={result.business_date} error={result.error_message}")

last_success = data_utils.get_last_retrieval(("SUCCESS", "DUPLICATE"))
last_failure = data_utils.get_last_retrieval(("HTTP_ERROR", "TIMEOUT", "PARSER_ERROR", "PRICE_NOT_FOUND"))
cols = st.columns(2)
cols[0].metric("Last successful retrieval",
                _fmt_ts(last_success["execution_time"]) if last_success else "None yet")
failed_label = f"Last failed retrieval ({last_failure['status']})" if last_failure else "Last failed retrieval"
cols[1].metric(failed_label, _fmt_ts(last_failure["execution_time"]) if last_failure else "None")

st.divider()
st.subheader("Retrieval log")
log_df = data_utils.get_retrieval_log(limit=200)
if log_df.empty:
    st.info("No retrieval attempts logged yet.")
else:
    status_options = ["All"] + sorted(log_df["status"].unique().tolist())
    status_filter = st.selectbox("Filter by status", status_options)
    view = log_df if status_filter == "All" else log_df[log_df["status"] == status_filter]
    st.dataframe(view, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Historical backfill import")
st.caption(
    "Upload a CSV or Excel file with columns `price_date` (YYYY-MM-DD) and `diesel_price`. "
    "An optional `fuel_type` column defaults to DIESEL; optional `currency`/`unit` columns default "
    "to USD / 1000 LTS (MEDCO's current published Diesel unit). Rows whose (date, fuel type) already "
    "exist are skipped, never overwritten."
)
uploaded = st.file_uploader("Backfill file", type=["csv", "xlsx"])
if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".csv"):
            import_df = pd.read_csv(uploaded, dtype=str)
        else:
            import_df = pd.read_excel(uploaded, dtype=str)
    except Exception as exc:  # noqa: BLE001 - surface any parse error to the user, don't crash the page
        st.error(f"Could not read file: {exc}")
        import_df = None

    if import_df is not None:
        missing_cols = {"price_date", "diesel_price"} - set(import_df.columns)
        if missing_cols:
            st.error(f"File is missing required column(s): {', '.join(sorted(missing_cols))}")
        else:
            st.write("Preview:")
            st.dataframe(import_df.head(20), use_container_width=True, hide_index=True)
            if st.button("Import rows"):
                summary = data_utils.import_backfill_rows(import_df.to_dict(orient="records"))
                st.success(
                    f"Imported {summary['imported']} row(s). "
                    f"Skipped {summary['skipped_duplicate']} duplicate(s). "
                    f"Rejected {summary['invalid']} invalid row(s)."
                )
