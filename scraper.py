"""Isolated MEDCO fuel-price scraper.

The `.fuel-prices` marquee on https://medco.com.lb/ ships completely empty in
the raw server HTML - it's a Next.js app and the marquee is populated by
client-side JavaScript with no discoverable JSON/XHR endpoint (verified by
capturing every network request a real browser makes while loading the page).
A plain `requests` call can never see the price, so this scrapes with a real
(headless) browser via Playwright instead.
"""
import re
import time
from dataclasses import dataclass, field

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import config

# e.g. "1,253.04 USD/1000LTS" or "2,471,000 LBP/20LTS" -> (value, currency, unit)
PRICE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*([A-Za-z.]+)\s*/\s*([\d,]+\s*[A-Za-z]+)")


@dataclass
class FuelEntry:
    label: str
    fuel_type: str
    price: float
    currency: str
    unit: str
    raw_value: str


@dataclass
class ScrapeResult:
    success: bool
    entries: dict = field(default_factory=dict)  # fuel_type -> FuelEntry
    status: str = "SUCCESS"
    error_message: str = None


def normalize_price_text(raw: str):
    """Extract (numeric price, currency, unit) from a raw marquee value string,
    e.g. 'Transportation + 1,253.04 USD/1000LTS' -> (1253.04, 'USD', '1000 LTS').
    Returns None if no recognizable price pattern is found - used generically
    for every fuel type, not hardcoded to a specific currency/unit.
    """
    match = PRICE_RE.search(raw)
    if not match:
        return None
    value_str, currency, unit = match.groups()
    try:
        price = float(value_str.replace(",", ""))
    except ValueError:
        return None
    unit = re.sub(r"(\d+)\s*([A-Za-z]+)", r"\1 \2", unit).strip()
    return price, currency.upper().strip(), unit


def _normalize_fuel_type(label: str) -> str:
    label = label.strip().upper()
    if "DIESEL" in label:
        return "DIESEL"
    if "95" in label:
        return "95"
    if "98" in label:
        return "98"
    if "LPG" in label:
        return "LPG"
    return label


def _extract_entries(marquee_text: str) -> dict:
    """marquee_text is the .fuel-prices innerText - alternating label/value
    lines (label identified by text, e.g. 'DIESEL', not by position, per the
    spec's resilience requirement):
        95
        2,471,000 LBP/20LTS
        DIESEL
        Transportation + 1,253.04 USD/1000LTS
        ...
    """
    lines = [ln.strip() for ln in marquee_text.splitlines() if ln.strip()]
    entries = {}
    i = 0
    while i + 1 < len(lines):
        label, value = lines[i], lines[i + 1]
        normalized = normalize_price_text(value)
        if normalized is None:
            i += 1
            continue
        price, currency, unit = normalized
        fuel_type = _normalize_fuel_type(label)
        entries[fuel_type] = FuelEntry(
            label=label, fuel_type=fuel_type, price=price,
            currency=currency, unit=unit, raw_value=value,
        )
        i += 2
    return entries


def _fetch_once(url: str, timeout_s: int) -> ScrapeResult:
    timeout_ms = timeout_s * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=config.SCRAPER_USER_AGENT)
            page = context.new_page()
            # "domcontentloaded" rather than "load": the page ships two
            # autoplaying background videos and a chat widget that make full
            # "load" slow and unnecessary - the price wait below is the real
            # readiness signal we need.
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError as exc:
                return ScrapeResult(success=False, status="TIMEOUT", error_message=str(exc))

            try:
                page.wait_for_function(
                    "sel => { const el = document.querySelector(sel); "
                    "return !!(el && el.innerText && el.innerText.trim().length > 0); }",
                    arg=".fuel-prices",
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError as exc:
                return ScrapeResult(
                    success=False, status="PRICE_NOT_FOUND",
                    error_message=f"'.fuel-prices' never populated within timeout: {exc}",
                )

            # First, non-duplicate marquee copy only (the second copy is an
            # exact aria-hidden duplicate used for the CSS scroll animation).
            el = page.query_selector(".fuel-prices > * > *:not([aria-hidden])")
            if el is None:
                el = page.query_selector(".fuel-prices")
            if el is None:
                return ScrapeResult(success=False, status="PRICE_NOT_FOUND",
                                     error_message="'.fuel-prices' element not found on page")
            text = el.inner_text()
        finally:
            browser.close()

    if not text or not text.strip():
        return ScrapeResult(success=False, status="PRICE_NOT_FOUND",
                             error_message="'.fuel-prices' element was empty")

    try:
        entries = _extract_entries(text)
    except Exception as exc:  # noqa: BLE001 - classify as a parser failure, not HTTP
        return ScrapeResult(success=False, status="PARSER_ERROR", error_message=str(exc))

    if config.FOCUS_FUEL_TYPE not in entries:
        return ScrapeResult(
            success=False, status="PRICE_NOT_FOUND",
            error_message=f"DIESEL label not found in marquee text: {text!r}",
            entries=entries,
        )

    return ScrapeResult(success=True, entries=entries, status="SUCCESS")


def fetch_fuel_prices(url: str = None, timeout_s: int = None, retries: int = None) -> ScrapeResult:
    """Fetch and parse the MEDCO fuel-prices marquee, with retries and
    exponential backoff. Never raises - all failures are reported via the
    returned ScrapeResult so callers (and the dashboard) can't be crashed by
    a MEDCO outage.
    """
    url = url or config.MEDCO_URL
    timeout_s = timeout_s or config.SCRAPER_TIMEOUT_SECONDS
    retries = retries if retries is not None else config.SCRAPER_MAX_RETRIES

    last_result = ScrapeResult(success=False, status="HTTP_ERROR", error_message="No attempts made")
    for attempt in range(retries + 1):
        try:
            last_result = _fetch_once(url, timeout_s)
        except PlaywrightTimeoutError as exc:
            last_result = ScrapeResult(success=False, status="TIMEOUT", error_message=str(exc))
        except PlaywrightError as exc:
            last_result = ScrapeResult(success=False, status="HTTP_ERROR", error_message=str(exc))
        except Exception as exc:  # noqa: BLE001 - scraper must never crash the caller
            last_result = ScrapeResult(success=False, status="HTTP_ERROR", error_message=str(exc))

        if last_result.success:
            return last_result
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))

    return last_result
