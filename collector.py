"""Orchestration layer implementing the daily collection flow (spec section 5):
connect -> extract -> validate/normalize -> determine business date ->
insert-or-correct-or-dedupe -> log. Both the Task Scheduler CLI
(run_scraper.py) and the dashboard's Refresh/Run Now buttons call
collector.run_once(), so there is exactly one code path for scraping (spec
section 3's data-collection/UI separation).
"""
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import data_utils
import scraper


@dataclass
class RunResult:
    success: bool
    status: str
    business_date: str = None
    inserted_fuel_types: list = field(default_factory=list)
    updated_fuel_types: list = field(default_factory=list)
    duplicate_fuel_types: list = field(default_factory=list)
    error_message: str = None


def business_date() -> str:
    """The date the price applies to (spec section 13) - Asia/Beirut's current
    calendar date, NOT the scrape's UTC retrieval timestamp.
    """
    tz = ZoneInfo(config.SCRAPER_TIMEZONE)
    return datetime.now(tz).date().isoformat()


def run_once() -> RunResult:
    """Runs the full flowchart from spec section 5 once. Never raises -
    scraper.fetch_fuel_prices() already reports failures instead of throwing,
    so a MEDCO outage always yields a logged failure, never a crash."""
    data_utils.init_db()
    business_date_str = business_date()

    result = scraper.fetch_fuel_prices()

    if not result.success:
        data_utils.log_retrieval(
            retrieval_date=business_date_str,
            source_url=config.MEDCO_URL,
            status=result.status,
            error_message=result.error_message,
            extracted_value=None,
        )
        return RunResult(success=False, status=result.status,
                          business_date=business_date_str, error_message=result.error_message)

    inserted, updated, duplicates = [], [], []
    for fuel_type, entry in result.entries.items():
        outcome = data_utils.insert_price_row(
            price_date=business_date_str,
            fuel_type=fuel_type,
            price=entry.price,
            currency=entry.currency,
            unit=entry.unit,
            retrieved_at=data_utils.now_iso(),
            raw_value=entry.raw_value,
            allow_price_correction=True,
        )
        if outcome == "INSERTED":
            inserted.append(fuel_type)
        elif outcome == "UPDATED":
            updated.append(fuel_type)
        else:
            duplicates.append(fuel_type)

    diesel_entry = result.entries.get(config.FOCUS_FUEL_TYPE)
    # A same-day price correction is just as much a "real" retrieval as a
    # fresh insert - it's the reason today's fuel_prices row (and therefore
    # the dashboard) now reflects MEDCO's current price, so it must count as
    # SUCCESS rather than DUPLICATE (see get_last_retrieval's SUCCESS/DUPLICATE
    # filter in app.py/pages/1_Admin.py).
    log_status = ("SUCCESS" if config.FOCUS_FUEL_TYPE in inserted or config.FOCUS_FUEL_TYPE in updated
                  else "DUPLICATE")
    data_utils.log_retrieval(
        retrieval_date=business_date_str,
        source_url=config.MEDCO_URL,
        status=log_status,
        error_message=None,
        extracted_value=diesel_entry.raw_value if diesel_entry else None,
    )

    return RunResult(
        success=True, status=log_status, business_date=business_date_str,
        inserted_fuel_types=inserted, updated_fuel_types=updated, duplicate_fuel_types=duplicates,
    )
