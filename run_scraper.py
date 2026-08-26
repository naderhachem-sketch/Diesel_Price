"""One-shot CLI entrypoint: run the MEDCO scrape-and-store pipeline once, then
exit. This is what Windows Task Scheduler calls daily (via run_scraper_now.bat)
and what the dashboard's Refresh/Run Now buttons call in-process - see
collector.run_once() for the actual logic.
"""
import sys

import collector


def main() -> int:
    result = collector.run_once()
    if result.success:
        print(f"[{result.status}] business_date={result.business_date} "
              f"inserted={result.inserted_fuel_types} duplicate={result.duplicate_fuel_types}")
        return 0
    print(f"[{result.status}] business_date={result.business_date} error={result.error_message}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
