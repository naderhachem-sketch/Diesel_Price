-- Live data store for the MEDCO Diesel Price Historization Dashboard.
-- fuel_prices holds one row per (price_date, fuel_type); the scraper reads
-- the whole MEDCO marquee on every run, so 95/98/LPG are captured too even
-- though the dashboard currently only surfaces DIESEL (see README).

CREATE TABLE IF NOT EXISTS fuel_prices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    price_date    TEXT    NOT NULL,             -- business date (Asia/Beirut), YYYY-MM-DD
    fuel_type     TEXT    NOT NULL,             -- 'DIESEL', '95', '98', 'LPG'
    price         REAL    NOT NULL,             -- numeric value as published
    currency      TEXT    NOT NULL,             -- as published, e.g. 'USD' or 'LBP'
    unit          TEXT    NOT NULL,             -- as published, e.g. '1000 LTS', '20 LTS', '10 KG'
    retrieved_at  TEXT    NOT NULL,             -- ISO-8601, when the scrape actually ran
    source        TEXT    NOT NULL DEFAULT 'MEDCO',
    status        TEXT    NOT NULL DEFAULT 'SUCCESS',
    raw_value     TEXT,                          -- untouched raw label text as scraped
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    UNIQUE(price_date, fuel_type)
);

CREATE TABLE IF NOT EXISTS retrieval_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_date    TEXT NOT NULL,             -- business date attempted
    execution_time    TEXT NOT NULL,             -- ISO-8601 timestamp of the run
    source_url        TEXT NOT NULL,
    status            TEXT NOT NULL,             -- SUCCESS/HTTP_ERROR/TIMEOUT/PARSER_ERROR/PRICE_NOT_FOUND/DUPLICATE
    error_message     TEXT,
    extracted_value   TEXT
);
