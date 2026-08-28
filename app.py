"""MEDCO Diesel Price History - main dashboard page: header, KPI cards, quick
filters, historical chart, and the historical data table with export.
"""
import io
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import collector
import config
import data_utils
import github_dispatch

st.set_page_config(page_title="MEDCO Diesel Price History", page_icon="⛽", layout="wide")

LINE_COLOR = "#2a78d6"
INCREASE_COLOR = "#2a78d6"
DECREASE_COLOR = "#e34948"
UNCHANGED_COLOR = "#898781"
GRIDLINE_COLOR = "#e1e0d9"
AXIS_COLOR = "#c3c2b7"
SYMBOL_MAP = {"increase": "triangle-up", "decrease": "triangle-down", "unchanged": "circle"}
COLOR_MAP = {"increase": INCREASE_COLOR, "decrease": DECREASE_COLOR, "unchanged": UNCHANGED_COLOR}
LABEL_MAP = {"increase": "Price Increase", "decrease": "Price Decrease", "unchanged": "No Change"}
ARROW_MAP = {"increase": "▲", "decrease": "▼", "unchanged": "—"}


def _prep_history(df: pd.DataFrame) -> pd.DataFrame:
    """Adds change/change_pct/direction columns, computed day-over-day across
    the full (unfiltered) history so a filtered view's first row still shows
    a correct change vs. the prior recorded price."""
    df = df.sort_values("price_date").reset_index(drop=True)
    df["prev_price"] = df["price"].shift(1)
    df["change"] = df["price"] - df["prev_price"]
    df["change_pct"] = (df["change"] / df["prev_price"]) * 100
    df["direction"] = df["change"].apply(
        lambda c: "unchanged" if pd.isna(c) or c == 0 else ("increase" if c > 0 else "decrease")
    )
    return df


def _fmt_kpi(price: float, currency: str) -> str:
    """Short form for KPI cards - the unit is shown once, in the chart axis
    label and table, rather than repeated (and truncated) in every card."""
    return f"{price:,.2f} {currency}"


def _quick_range_dates(min_date: date, max_date: date, days=None, months=None, all_time=False):
    if all_time:
        return min_date, max_date
    if months is not None:
        days = months * 30
    frm = max(min_date, max_date - timedelta(days=days))
    return frm, max_date


def _apply_quick_range(min_date, max_date, from_key, to_key, **kwargs):
    frm, to = _quick_range_dates(min_date, max_date, **kwargs)
    st.session_state[from_key] = frm
    st.session_state[to_key] = to


def render_header():
    st.title("MEDCO Diesel Price History")
    st.caption("Source: MEDCO Lebanon")
    last_success = data_utils.get_last_retrieval(("SUCCESS", "DUPLICATE"))
    if last_success is not None:
        retrieved_at = pd.to_datetime(last_success["execution_time"]).strftime("%d-%b-%Y %H:%M")
        st.caption(f"Last Updated: {retrieved_at}")
    else:
        st.caption("Last Updated: never - no successful retrieval yet")


def render_kpis(history: pd.DataFrame, fuel_label: str):
    top = st.columns(3)
    if history.empty:
        top[0].metric(f"Current {fuel_label} price", "No data yet")
        for c in top[1:]:
            c.metric("—", "—")
        return

    latest = history.iloc[-1]
    previous = history.iloc[-2] if len(history) >= 2 else None
    unit = latest["unit"]
    currency = latest["currency"]

    top[0].metric(f"Current {fuel_label} price", _fmt_kpi(latest["price"], currency))

    if previous is not None:
        top[1].metric("Previous price", _fmt_kpi(previous["price"], currency))
        change = latest["price"] - previous["price"]
        change_pct = (change / previous["price"]) * 100 if previous["price"] else 0.0
        top[2].metric("Change", f"{change:+,.2f} {currency}", delta=f"{change_pct:+.2f}%")
    else:
        top[1].metric("Previous price", "No prior record")
        top[2].metric("Change", "N/A")

    bottom = st.columns(2)
    bottom[0].metric("Highest recorded", _fmt_kpi(history["price"].max(), currency))
    bottom[1].metric("Lowest recorded", _fmt_kpi(history["price"].min(), currency))
    st.caption(f"All prices in {currency} per {unit}")


def build_chart(df: pd.DataFrame, currency: str, unit: str, fuel_label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["price_date"], y=df["price"], mode="lines",
        line=dict(color=LINE_COLOR, width=2), hoverinfo="skip", showlegend=False,
    ))

    for direction in ["increase", "decrease", "unchanged"]:
        sub = df[df["direction"] == direction]
        if sub.empty:
            continue
        change_vals = sub["change"].fillna(0).values
        change_pct_vals = sub["change_pct"].fillna(0).values
        fig.add_trace(go.Scatter(
            x=sub["price_date"], y=sub["price"], mode="markers",
            marker=dict(size=10, color=COLOR_MAP[direction], symbol=SYMBOL_MAP[direction],
                        line=dict(width=2, color="#fcfcfb")),
            name=LABEL_MAP[direction],
            customdata=list(zip(change_vals, change_pct_vals)),
            hovertemplate=(
                "<b>%{x|%d-%b-%Y}</b><br>"
                f"{fuel_label} Price: %{{y:,.2f}} {currency}<br>"
                "Change vs. previous: %{customdata[0]:+,.2f} (%{customdata[1]:+.2f}%)"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=f"{fuel_label} Price ({currency} / {unit})",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRIDLINE_COLOR, showline=True, linecolor=AXIS_COLOR),
        yaxis=dict(gridcolor=GRIDLINE_COLOR, showline=True, linecolor=AXIS_COLOR, tickformat=",.0f"),
        margin=dict(t=10, b=10, l=10, r=10),
        height=450,
    )
    return fig


def render_filters(min_date: date, max_date: date, fuel_type: str):
    from_key, to_key = f"from_date_{fuel_type}", f"to_date_{fuel_type}"
    if from_key not in st.session_state:
        st.session_state[from_key] = min_date
    if to_key not in st.session_state:
        st.session_state[to_key] = max_date

    st.write("**Quick filters**")
    preset_cols = st.columns(6)
    preset_args = (min_date, max_date, from_key, to_key)
    preset_cols[0].button("Last 7 Days", key=f"preset_7d_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"days": 7})
    preset_cols[1].button("Last 30 Days", key=f"preset_30d_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"days": 30})
    preset_cols[2].button("Last 3 Months", key=f"preset_3m_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"months": 3})
    preset_cols[3].button("Last 6 Months", key=f"preset_6m_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"months": 6})
    preset_cols[4].button("Last 12 Months", key=f"preset_12m_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"months": 12})
    preset_cols[5].button("All Time", key=f"preset_all_{fuel_type}",
                           on_click=_apply_quick_range, args=preset_args, kwargs={"all_time": True})

    date_cols = st.columns(2)
    date_cols[0].date_input("From Date", min_value=min_date, max_value=max_date, key=from_key)
    date_cols[1].date_input("To Date", min_value=min_date, max_value=max_date, key=to_key)

    return st.session_state[from_key], st.session_state[to_key]


def render_change_counts(filtered: pd.DataFrame):
    counted = filtered.iloc[1:] if len(filtered) > 1 else filtered.iloc[0:0]
    increases = (counted["direction"] == "increase").sum()
    decreases = (counted["direction"] == "decrease").sum()
    unchanged = (counted["direction"] == "unchanged").sum()
    st.caption(f"▲ {increases} increase(s)  ·  ▼ {decreases} decrease(s)  ·  — {unchanged} unchanged day(s)")


def render_table(filtered: pd.DataFrame, fuel_type: str, fuel_label: str):
    st.subheader("Historical Data")

    source_options = ["All"] + sorted(filtered["source"].unique().tolist()) if not filtered.empty else ["All"]
    source_filter = st.selectbox("Filter by source", source_options, key=f"source_filter_{fuel_type}")

    table = filtered.sort_values("price_date", ascending=False).copy()
    if source_filter != "All":
        table = table[table["source"] == source_filter]

    display = pd.DataFrame({
        "Date": table["price_date"].dt.strftime("%d-%b-%Y"),
        f"{fuel_label} Price": table["price"].map(lambda v: f"{v:,.2f}"),
        "Trend": table["direction"].map(lambda d: ARROW_MAP.get(d, "—")),
        "Change": table["change"].map(lambda v: f"{v:+,.2f}" if pd.notna(v) else "—"),
        "Change %": table["change_pct"].map(lambda v: f"{v:+.2f}%" if pd.notna(v) else "—"),
        "Retrieved At": pd.to_datetime(table["retrieved_at"]).dt.strftime("%d-%b-%Y %H:%M"),
        "Status": table["status"],
        "Source": table["source"],
    })

    page_size = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key=f"page_size_{fuel_type}")
    total_pages = max(1, -(-len(display) // page_size))
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key=f"page_{fuel_type}")
    start = (page - 1) * page_size
    st.dataframe(display.iloc[start:start + page_size], use_container_width=True, hide_index=True)
    st.caption(f"Page {page} of {total_pages} · {len(display)} row(s)")

    file_stem = f"{fuel_type.lower()}_price_history"
    export_cols = st.columns(2)
    csv_bytes = table_for_export(table, fuel_label).to_csv(index=False).encode("utf-8")
    export_cols[0].download_button("Export to CSV", csv_bytes, f"{file_stem}.csv", "text/csv",
                                    key=f"export_csv_{fuel_type}")

    excel_buf = io.BytesIO()
    table_for_export(table, fuel_label).to_excel(excel_buf, index=False, engine="openpyxl")
    export_cols[1].download_button(
        "Export to Excel", excel_buf.getvalue(), f"{file_stem}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"export_xlsx_{fuel_type}",
    )


def table_for_export(table: pd.DataFrame, fuel_label: str) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": table["price_date"].dt.strftime("%Y-%m-%d"),
        f"{fuel_label} Price": table["price"],
        "Currency": table["currency"],
        "Unit": table["unit"],
        "Change": table["change"],
        "Change %": table["change_pct"],
        "Retrieved At": table["retrieved_at"],
        "Status": table["status"],
        "Source": table["source"],
    })


def render_fuel_tab(fuel_type: str):
    fuel_label = config.FUEL_LABELS.get(fuel_type, fuel_type)
    history = data_utils.get_fuel_history(fuel_type)
    history = _prep_history(history) if not history.empty else history

    today_str = collector.business_date()
    if history.empty or history.iloc[-1]["price_date"].date().isoformat() != today_str:
        st.warning(f"Today's ({today_str}) {fuel_label} price has not been retrieved yet. "
                   f"Showing the last successfully retrieved price below.")

    render_kpis(history, fuel_label)
    st.divider()

    if history.empty:
        st.info(f"No historical {fuel_label} price data yet. Click Refresh above, or wait for the "
                 "daily scheduled run, or import historical data from the Admin page.")
        return

    min_date = history["price_date"].min().date()
    max_date = history["price_date"].max().date()
    from_date, to_date = render_filters(min_date, max_date, fuel_type)

    mask = (history["price_date"].dt.date >= from_date) & (history["price_date"].dt.date <= to_date)
    filtered = history[mask]

    st.subheader(f"{fuel_label} Price History")
    if filtered.empty:
        st.info("No data in the selected date range.")
    else:
        latest = history.iloc[-1]
        st.plotly_chart(build_chart(filtered, latest["currency"], latest["unit"], fuel_label),
                         use_container_width=True, key=f"chart_{fuel_type}")
        render_change_counts(filtered)

    st.divider()
    render_table(filtered, fuel_type, fuel_label)


def main():
    data_utils.init_db()
    render_header()

    if st.button("🔄 Refresh MEDCO Price"):
        if github_dispatch.github_token():
            # Streamlit Cloud can't launch a real Chromium (see scraper.py's
            # docstring) - dispatch the GitHub Actions job instead of
            # scraping in-process. Same as the Admin page's Run Now button.
            with st.spinner("Triggering GitHub Actions..."):
                ok, message = github_dispatch.trigger_github_scrape()
            st.session_state["last_refresh_dispatch"] = (ok, message)
        else:
            with st.spinner("Contacting MEDCO..."):
                result = collector.run_once()
            st.session_state["last_refresh_result"] = result
        st.rerun()

    if "last_refresh_dispatch" in st.session_state:
        ok, message = st.session_state.pop("last_refresh_dispatch")
        if ok:
            st.success(f"{message} The new price will appear here in a few minutes, once the "
                       "job finishes and the app redeploys - refresh this page again shortly.")
        else:
            st.error(message)

    if "last_refresh_result" in st.session_state:
        result = st.session_state.pop("last_refresh_result")
        if result.success:
            st.success(f"Retrieved successfully ({result.status}) for {result.business_date}.")
        else:
            st.error(f"Retrieval failed: {result.status} - {result.error_message}")

    last_success = data_utils.get_last_retrieval(("SUCCESS", "DUPLICATE"))
    last_failure = data_utils.get_last_retrieval(
        ("HTTP_ERROR", "TIMEOUT", "PARSER_ERROR", "PRICE_NOT_FOUND")
    )
    status_cols = st.columns(2)
    status_cols[0].caption(
        f"Last successful retrieval: {last_success['execution_time']}" if last_success
        else "Last successful retrieval: none yet"
    )
    status_cols[1].caption(
        f"Last failed retrieval: {last_failure['execution_time']} ({last_failure['status']})" if last_failure
        else "Last failed retrieval: none"
    )

    st.divider()

    tabs = st.tabs([config.FUEL_LABELS.get(ft, ft) for ft in config.FUEL_TYPE_ORDER])
    for tab, fuel_type in zip(tabs, config.FUEL_TYPE_ORDER):
        with tab:
            render_fuel_tab(fuel_type)


main()
