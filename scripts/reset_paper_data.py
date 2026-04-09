"""Reset persisted paper-trading state for one or more markets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings
from db.persistence import PersistenceManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear persisted paper-trading state from MySQL.",
    )
    parser.add_argument(
        "--market",
        choices=("US", "INDIA", "ALL"),
        default="INDIA",
        help="Market ledger to clear. Use ALL to reset both ledgers.",
    )
    parser.add_argument(
        "--clear-watchlist",
        action="store_true",
        help="Also remove the persisted watchlist for the selected market(s).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    persistence = PersistenceManager()
    persistence.initialize()
    try:
        if not persistence.enabled:
            print("Persistence is disabled; nothing to reset.")
            return 0

        markets = ("US", "INDIA") if args.market == "ALL" else (args.market,)
        for market in markets:
            persistence.reset_market_state(market, clear_watchlist=args.clear_watchlist)
            print(
                f"Reset persisted paper-trading state for {market}"
                + (" including watchlist." if args.clear_watchlist else ".")
            )
        print(
            "Next startup will use ACTIVE_MARKET="
            f"{settings.active_market} unless you override it in the environment or .env."
        )
        return 0
    finally:
        persistence.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
