# MEDCO Diesel Price Historization Dashboard

Build a web-based dashboard that automatically retrieves and historizes the **daily Diesel price published by MEDCO Lebanon**.

## 1. Data Source

The source website is:

MEDCO Lebanon: https://medco.com.lb/

The Diesel price is displayed on the MEDCO website inside:

```html
<div class="fuel-prices"></div>
```

This element is a **marquee/banner** that displays the current daily fuel prices.

The application must identify and extract the **Diesel price** from this section.

Do not hardcode the Diesel price.

The scraper/parser should be resilient to minor changes in the HTML structure and should clearly identify the Diesel value based on its label rather than relying only on a fixed position.

## 2. Main Objective

Create an automated historization system that:

1. Connects to the MEDCO website once per day.
2. Reads the Diesel price from the `fuel-prices` section.
3. Extracts the Diesel price.
4. Stores the price together with the date/time of retrieval.
5. Prevents duplicate records for the same business date.
6. Maintains historical records permanently.
7. Displays the historical Diesel prices in a dashboard.
8. Shows how the Diesel price has changed over time using charts.

The dashboard should continue to work even when the MEDCO website is temporarily unavailable because historical data must be stored locally/in the application's database.

---

# 3. Recommended Architecture

Use the following logical architecture:

```text
MEDCO Website
     │
     │ Daily HTTP Request
     ▼
Scraper / Data Collector
     │
     │ Extract Diesel Price
     ▼
Validation / Normalization
     │
     ▼
Database
     │
     ├── Historical Diesel Prices
     │
     └── Retrieval / Error Logs
     │
     ▼
Dashboard
     │
     ├── Current Price
     ├── Historical Chart
     ├── Daily History Table
     ├── Statistics
     └── Price Changes
```

Separate the **data collection layer** from the **dashboard UI**.

The dashboard should read from the database rather than scraping MEDCO every time a user opens the dashboard.

---

# 4. Database

Use SQLite by default unless the existing project already uses another database.

Create a table similar to:

```sql
diesel_prices
```

Suggested fields:

```text
id
price_date
diesel_price
currency
retrieved_at
source
status
raw_value
created_at
updated_at
```

Example:

```text
id: 1
price_date: 2026-08-26
diesel_price: 138500
currency: LBP
retrieved_at: 2026-08-26 09:00:15
source: MEDCO
status: SUCCESS
raw_value: "Diesel: 138,500 L.L."
```

Add a unique constraint/index on:

```text
price_date
```

This prevents the scheduler from inserting the same daily price multiple times.

---

# 5. Daily Data Collection

Implement a scheduled job that runs automatically once per day.

The scheduler should:

1. Request the MEDCO website.
2. Locate:

```html
<div class="fuel-prices"></div>
```

3. Extract the text/content.
4. Identify the Diesel price.
5. Clean the value.
6. Convert it into a numeric value.
7. Determine the current business date.
8. Check whether a record already exists for that date.
9. Insert the price if it does not exist.
10. Log the result.

Example logic:

```text
START
  ↓
Connect to MEDCO
  ↓
HTTP request successful?
  ├── NO → Log error → Retry → Stop
  │
  └── YES
       ↓
Find .fuel-prices
       ↓
Find Diesel price
       ↓
Price successfully extracted?
  ├── NO → Log extraction error
  │
  └── YES
       ↓
Normalize price
       ↓
Does today's record already exist?
  ├── YES → Update/validate existing record
  │
  └── NO → Insert new record
       ↓
Log successful retrieval
       ↓
END
```

## Important

The scraper must not blindly assume that the Diesel price is always in the same HTML position.

For example, if the marquee contains:

```text
95 Octane: ...
98 Octane: ...
Diesel: ...
```

the code should search for the **Diesel label** and extract the associated value.

---

# 6. Retry and Error Handling

Implement robust error handling.

If MEDCO cannot be reached:

* Retry the request.
* Use a reasonable timeout.
* Log the failure.
* Do not overwrite existing historical data.
* Display the last successfully retrieved price on the dashboard.
* Clearly indicate that today's price has not yet been retrieved.

Create an application log/table for:

```text
retrieval_date
execution_time
source_url
status
error_message
extracted_value
```

Possible statuses:

```text
SUCCESS
HTTP_ERROR
TIMEOUT
PARSER_ERROR
PRICE_NOT_FOUND
DUPLICATE
```

---

# 7. Dashboard

Create a clean and professional dashboard.

## Header

Display:

**MEDCO Diesel Price History**

Under the title show:

```text
Source: MEDCO Lebanon
Last Updated: DD-MMM-YYYY HH:MM
```

---

# 8. KPI Cards

Create the following cards:

### Current Diesel Price

Display the latest successfully retrieved Diesel price.

### Previous Price

Display the previous recorded price.

### Change

Show:

```text
Current Price - Previous Price
```

Also show the percentage change:

```text
((Current - Previous) / Previous) × 100
```

### Highest Price

Display the highest recorded Diesel price.

### Lowest Price

Display the lowest recorded Diesel price.

---

# 9. Historical Chart

Create a time-series line chart:

```text
Diesel Price
     │
     │                     ●
     │                ●────┘
     │          ●─────┘
     │     ●────┘
     │ ●───┘
     └────────────────────────
       Date
```

X-axis:

```text
Date
```

Y-axis:

```text
Diesel Price (LBP)
```

Each point represents the Diesel price recorded for that day.

Add tooltips showing:

```text
Date
Diesel Price
Change from previous recorded price
```

---

# 10. Filters

Add dashboard filters:

### Date Range

Allow users to select:

```text
From Date
To Date
```

### Quick Filters

Provide:

```text
Last 7 Days
Last 30 Days
Last 3 Months
Last 6 Months
Last 12 Months
All Time
```

The chart and statistics should update dynamically.

---

# 11. Historical Data Table

Add a table below the chart:

| Date        | Diesel Price | Change | Change % | Retrieved At | Status  |
| ----------- | -----------: | -----: | -------: | ------------ | ------- |
| 26-Aug-2026 |      138,500 | +2,500 |   +1.84% | 09:00        | SUCCESS |
| 25-Aug-2026 |      136,000 |      0 |       0% | 09:01        | SUCCESS |

Allow:

* Sorting
* Filtering
* Pagination
* Export to Excel/CSV

---

# 12. Price Change Visualization

Highlight days where the price changed.

For example:

```text
▲ Price Increase
▼ Price Decrease
— No Change
```

On the chart, make price changes easy to identify.

Also calculate:

```text
Number of price increases
Number of price decreases
Number of unchanged days
```

---

# 13. Data Integrity

The application must distinguish between:

### Business Date

The date for which the Diesel price applies.

and:

### Retrieval Date/Time

When the application actually retrieved the value from MEDCO.

This is important because the scraper might run at 08:00, 09:00, or later.

Do not use retrieval timestamp as the historical business date.

---

# 14. Scheduler

Implement an automatic daily scheduler.

Default schedule:

```text
Every day at 09:00 Lebanon time
```

Use the timezone:

```text
Asia/Beirut
```

Make the schedule configurable through configuration/environment variables.

For example:

```text
SCRAPER_TIME=09:00
SCRAPER_TIMEZONE=Asia/Beirut
```

Also provide a **"Run Now"** button in an admin/data-management section so the scraper can be manually triggered.

---

# 15. Manual Refresh

Add:

**Refresh MEDCO Price**

When clicked:

1. Call the MEDCO scraper.
2. Retrieve the current price.
3. Validate it.
4. Store it if necessary.
5. Refresh the dashboard.

Show:

```text
Last successful retrieval
Last failed retrieval
```

---

# 16. Historical Backfill

Provide an optional mechanism to import historical Diesel prices from a CSV/Excel file.

The imported data should follow the same database structure.

Example:

```csv
price_date,diesel_price
2026-08-20,132000
2026-08-21,134000
2026-08-22,134000
```

This allows historical data to be populated before the automated scraper starts.

Imported records should also respect the unique `price_date` constraint.

---

# 17. Future-Proofing

Design the database so that additional fuel types can be added later.

Instead of creating a separate table for every fuel type, consider a structure such as:

```text
fuel_prices

id
price_date
fuel_type
price
currency
retrieved_at
source
status
```

Then the application could eventually support:

```text
Diesel
95 Octane
98 Octane
```

However, the initial dashboard should focus on **Diesel**.

---

# 18. Security and Reliability

Do not expose credentials or sensitive configuration in the source code.

Use environment variables where necessary.

Add:

* Request timeout
* Retry mechanism
* User-Agent
* Logging
* Input validation
* Database constraints
* Duplicate prevention
* Graceful failure handling

Do not allow the dashboard to crash if MEDCO is unavailable.

---

# 19. Dashboard Design

Use a modern, clean dashboard suitable for desktop use.

Recommended layout:

```text
┌─────────────────────────────────────────────────────┐
│          MEDCO DIESEL PRICE HISTORY                 │
│          Last Updated: 26-Aug-2026 09:00            │
├─────────────┬─────────────┬─────────────┬───────────┤
│ Current     │ Previous    │ Change      │ Highest   │
│ 138,500 LBP │ 136,000 LBP │ +1.84% ▲    │ 145,000   │
├─────────────┴─────────────┴─────────────┴───────────┤
│                                                     │
│              DIESEL PRICE HISTORY                   │
│                                                     │
│          📈 Historical Line Chart                   │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Date Range: [From] [To]                             │
│                                                     │
│ Historical Data                                     │
│ Date       Price       Change       Change %        │
│ ─────────────────────────────────────────────────── │
│ 26-Aug     138,500     +2,500       +1.84%          │
│ 25-Aug     136,000          0        0.00%          │
└─────────────────────────────────────────────────────┘
```

---

# 20. Technical Requirements

Before implementing the scraper, inspect the actual MEDCO website and verify:

* Current HTML structure
* `.fuel-prices` contents
* How the marquee is generated
* Whether the price is present directly in the HTML
* Whether JavaScript is required to render the price
* Exact Diesel label/value format
* Currency representation
* Whether the website has anti-bot/rate-limiting mechanisms

If the value is generated dynamically with JavaScript, use an appropriate browser automation solution such as Playwright rather than assuming a simple HTTP request will always contain the price.

Keep the scraper isolated in its own module so it can be modified easily if MEDCO changes its website.

---

# 21. Deliverables

Produce a complete working application containing:

1. Dashboard UI
2. MEDCO Diesel scraper
3. Database schema
4. Daily scheduler
5. Historical price storage
6. Duplicate prevention
7. Error logging
8. Manual "Run Now" functionality
9. Historical price chart
10. KPI cards
11. Date filters
12. Historical data table
13. CSV/Excel export
14. Optional historical data import
15. README with installation and setup instructions
16. `.env.example`
17. Database initialization/migration script
18. Instructions for running the daily scheduler in production

Before considering the implementation complete, test the scraper against the live MEDCO website and demonstrate that the Diesel price is correctly extracted and stored in the database.
