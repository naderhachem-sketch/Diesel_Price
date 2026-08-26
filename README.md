# MEDCO Diesel Price History

A Streamlit dashboard that scrapes the daily fuel prices published by
[MEDCO Lebanon](https://medco.com.lb/) - Diesel, 95 Octane, 98 Octane, and
LPG - historizes them in a local SQLite database, and visualizes how each
changes over time.

## Setup

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

`playwright install chromium` is a one-time download of a headless Chromium
build (~150-300MB) - it does not ship with the `playwright` pip package.

Copy `.env.example` to `.env` if you want to override any default (source
URL, scheduler time, timeouts, retries, db path) - every value already has a
sensible built-in default, so `.env` is optional.

## Run

```bat
run_dashboard.bat
```
or directly: `.venv\Scripts\python.exe -m streamlit run app.py`

The dashboard reads only from the local SQLite database (`diesel_price.db`)
- it never scrapes MEDCO on page load, so it keeps working (showing the last
known price) even when MEDCO is unreachable.

## Data source

`https://medco.com.lb/` renders its fuel-price marquee (`<div class="fuel-prices">`)
entirely with client-side JavaScript - the raw HTML response never contains
the price, even on a complete download (verified by inspecting the live site
and every network request a real browser makes while loading it: no separate
JSON/price API exists either). `scraper.py` therefore drives a headless
Chromium browser (Playwright) instead of a plain HTTP request.

The marquee currently exposes four fuel types (`95`, `98`, `DIESEL`, `LPG`);
the scraper reads all of them by label text (not by position, so it survives
MEDCO re-ordering the marquee) and stores each in the generic `fuel_prices`
table (`fuel_type` column). The dashboard surfaces all four as tabs (Diesel,
95 Octane, 98 Octane, LPG) - one scrape run updates all of them together,
each with its own KPI cards, chart, filters and table, in the currency/unit
it's actually published in (no fuel type's display logic hardcodes LBP/USD).
**Diesel is currently published in USD per 1000 litres** (e.g.
`Transportation + 1,253.04 USD/1000LTS`), unlike 95/98/LPG which are in LBP -
the schema stores whatever currency/unit MEDCO actually publishes per row
(`currency`, `unit` columns) rather than assuming one.

`price_date` (the business date the price applies to, Asia/Beirut) is always
kept distinct from `retrieved_at` (the UTC timestamp the scrape actually
ran) - the scheduler may run a little late on any given day, and the price
must still be attributed to the correct calendar date.

## Calculation logic

Every formula below is computed **independently per fuel type tab** - e.g.
switching to the LPG tab recomputes Current/Previous/Highest/Lowest/etc. from
LPG's own rows only, and each tab keeps its own date-range filter selection.

- **Current / Previous** - the most recent and second-most-recent
  `price_date` rows for that tab's `fuel_type`, regardless of the chart's
  date filter (these two KPI cards always reflect that fuel's full history).
- **Change** = Current − Previous. **Change %** = (Current − Previous) /
  Previous × 100.
- **Highest / Lowest** = max/min of `price` across *all* recorded history for
  that fuel type (not filtered by the date range picker).
- **▲ / ▼ / —** (the chart legend/markers and the table's Trend column) - a
  day is an increase/decrease/unchanged relative to the previous *recorded*
  price for that fuel type (not necessarily the previous calendar day, if a
  day was missed). The first ever recorded row has no prior day and counts
  as unchanged.
- The **increase/decrease/unchanged counts** shown under the chart are
  computed over the currently filtered date range.
- CSV/Excel export reflects exactly the rows currently visible in that tab's
  table (i.e. after the date-range and source filters), one file per fuel
  type (`{fuel_type}_price_history.csv`/`.xlsx`).
- **Last Updated** (page header) and **Last successful retrieval** reflect
  the most recent scrape attempt that reached MEDCO (`SUCCESS` or
  `DUPLICATE`), across all fuel types - not any one tab's latest row - since
  a single scrape run always updates all four together.

> Keep this section in sync whenever any KPI or chart formula changes.

## Scheduler (production)

The scraper is a one-shot script (`run_scraper.py`) - nothing needs to stay
running. Register it in Windows Task Scheduler to run daily at
`SCRAPER_TIME` (default `10:30`, `SCRAPER_TIMEZONE` default `Asia/Beirut`):

```bat
schtasks /create /tn "MEDCO Diesel Scraper" /tr "C:\path\to\Diesel Price\run_scraper_now.bat" /sc daily /st 10:30 /f
```

Adjust the `/st` time to match `SCRAPER_TIME` if you change it in `.env`.
You can verify/trigger it manually from Task Scheduler, or just run
`run_scraper_now.bat` directly, or use the **Run Now** button on the Admin
page - all three paths call the exact same `collector.run_once()` function,
so behavior is identical.

## Historical backfill

If you have real historical Diesel prices (e.g. from a spreadsheet), import
them from the **Admin** page: upload a CSV/Excel file with `price_date`
(`YYYY-MM-DD`) and `diesel_price` columns (optional `fuel_type`, `currency`,
`unit`). Duplicate `(price_date, fuel_type)` rows are skipped, never
overwritten - existing history is never lost.

## Pages

- **Dashboard** (`app.py`) - shared header and Refresh button, then one tab
  per fuel type (Diesel, 95 Octane, 98 Octane, LPG). Each tab has its own KPI
  cards, quick date filters, historical price chart, and historical data
  table with CSV/Excel export. The set and order of tabs is driven by
  `config.FUEL_TYPE_ORDER`/`FUEL_LABELS`.
- **Admin** (`pages/1_Admin.py`) - manual Run Now trigger, last
  success/failure timestamps, the full retrieval log, and the historical
  backfill importer (works for any fuel type via the CSV's optional
  `fuel_type` column).

## Project structure

```
app.py               Main dashboard page
pages/1_Admin.py      Admin / data-management page
data_utils.py         SQLite connection, schema init, all queries
scraper.py            Isolated MEDCO scraper (Playwright)
collector.py           Orchestration: business date, dedupe, insert, log
run_scraper.py         CLI one-shot entrypoint (Task Scheduler target)
config.py              Env var loading, all tunables
schema.sql             fuel_prices + retrieval_log tables
.env.example           Documented, all-optional configuration
run_dashboard.bat       Launch the dashboard
run_scraper_now.bat     Run one scrape (Task Scheduler target)
```
