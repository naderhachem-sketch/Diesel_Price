"""SQLite connection, schema init, and all read/write queries for the MEDCO
Diesel Price dashboard. Used by app.py, pages/1_Admin.py, and collector.py.
"""
import sqlite3
from datetime import datetime, timezone

import pandas as pd

import config

DB_PATH = config.DB_PATH
SCHEMA_PATH = config.SCHEMA_PATH


def _db_connect(db_path=DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path=DB_PATH) -> None:
    """Create fuel_prices/retrieval_log (and enable WAL mode) if they don't
    already exist. Safe to call every time the app or scraper starts."""
    conn = _db_connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute("PRAGMA journal_mode = WAL")
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- fuel_prices

def record_exists(price_date: str, fuel_type: str, db_path=DB_PATH) -> bool:
    conn = _db_connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM fuel_prices WHERE price_date = ? AND fuel_type = ?",
            (price_date, fuel_type),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_price_row(
    price_date: str,
    fuel_type: str,
    price: float,
    currency: str,
    unit: str,
    retrieved_at: str,
    raw_value: str,
    source: str = "MEDCO",
    status: str = "SUCCESS",
    db_path=DB_PATH,
) -> str:
    """Insert a new fuel_prices row. Returns 'INSERTED' or 'DUPLICATE' (existing
    historical rows are never overwritten - see spec section 6/13)."""
    if record_exists(price_date, fuel_type, db_path=db_path):
        return "DUPLICATE"
    ts = now_iso()
    conn = _db_connect(db_path)
    try:
        with conn:
            conn.execute(
                """INSERT INTO fuel_prices
                   (price_date, fuel_type, price, currency, unit, retrieved_at,
                    source, status, raw_value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (price_date, fuel_type, price, currency, unit, retrieved_at,
                 source, status, raw_value, ts, ts),
            )
        return "INSERTED"
    finally:
        conn.close()


def get_fuel_history(fuel_type=config.FOCUS_FUEL_TYPE, db_path=DB_PATH) -> pd.DataFrame:
    conn = _db_connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM fuel_prices WHERE fuel_type = ? ORDER BY price_date ASC",
            conn,
            params=(fuel_type,),
        )
    finally:
        conn.close()
    if not df.empty:
        df["price_date"] = pd.to_datetime(df["price_date"])
    return df


# -------------------------------------------------------------- retrieval_log

def log_retrieval(
    retrieval_date: str,
    source_url: str,
    status: str,
    error_message: str = None,
    extracted_value: str = None,
    db_path=DB_PATH,
) -> None:
    conn = _db_connect(db_path)
    try:
        with conn:
            conn.execute(
                """INSERT INTO retrieval_log
                   (retrieval_date, execution_time, source_url, status, error_message, extracted_value)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (retrieval_date, now_iso(), source_url, status, error_message, extracted_value),
            )
    finally:
        conn.close()


def get_retrieval_log(limit: int = 200, db_path=DB_PATH) -> pd.DataFrame:
    conn = _db_connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM retrieval_log ORDER BY id DESC LIMIT ?",
            conn,
            params=(limit,),
        )
    finally:
        conn.close()
    return df


def get_last_retrieval(status_in: tuple, db_path=DB_PATH):
    """Most recent retrieval_log row whose status is in status_in, or None."""
    placeholders = ",".join("?" for _ in status_in)
    conn = _db_connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"SELECT * FROM retrieval_log WHERE status IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 1",
            status_in,
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


# ------------------------------------------------------------------ backfill

def import_backfill_rows(rows: list, db_path=DB_PATH) -> dict:
    """rows: list of dicts with keys price_date (YYYY-MM-DD), diesel_price,
    and optionally fuel_type/currency/unit. Respects the unique
    (price_date, fuel_type) constraint - duplicates are skipped, not overwritten.
    """
    imported, skipped_duplicate, invalid = 0, 0, 0
    for row in rows:
        try:
            price_date = str(row["price_date"]).strip()
            price = float(row["diesel_price"])
            fuel_type = str(row.get("fuel_type") or config.FOCUS_FUEL_TYPE).strip().upper()
            currency = str(row.get("currency") or "USD").strip()
            unit = str(row.get("unit") or "1000 LTS").strip()
            if not price_date or price <= 0:
                invalid += 1
                continue
        except (KeyError, ValueError, TypeError):
            invalid += 1
            continue

        result = insert_price_row(
            price_date=price_date,
            fuel_type=fuel_type,
            price=price,
            currency=currency,
            unit=unit,
            retrieved_at=now_iso(),
            raw_value=f"Backfill import: {price} {currency}/{unit}",
            source="BACKFILL",
            status="SUCCESS",
            db_path=db_path,
        )
        if result == "INSERTED":
            imported += 1
        else:
            skipped_duplicate += 1

    return {"imported": imported, "skipped_duplicate": skipped_duplicate, "invalid": invalid}
