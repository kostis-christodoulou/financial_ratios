from __future__ import annotations

import argparse
import json
from pathlib import Path

from finstat.config import load_settings
from finstat.db.connection import init_db
from finstat.db.repositories import FinancialRepository
from finstat.web.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="finstat")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    refresh = sub.add_parser("refresh")
    refresh.add_argument("ticker")
    refresh.add_argument("--years", nargs="*", type=int, default=None)
    refresh.add_argument("--refresh-http", action="store_true")

    ratios = sub.add_parser("ratios")
    ratios.add_argument("ticker")
    ratios.add_argument("--json", action="store_true")

    export = sub.add_parser("export")
    export.add_argument("ticker")
    export.add_argument("--out", default=None)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "init-db":
        init_db(settings.db_path)
        print(f"Initialized {settings.db_path}")
        return

    repo = FinancialRepository(settings)

    if args.command == "refresh":
        company = repo.refresh_company(args.ticker, years=args.years, refresh_http=args.refresh_http)
        print(f"Refreshed {company['ticker']} / CIK {company['cik']} / {company['name']}")
    elif args.command == "ratios":
        overview = repo.company_overview(args.ticker)
        data = overview.get("ratios", [])
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            for row in data:
                value = row["value"]
                display = "n/a" if value is None else f"{value:.4f}"
                print(
                    f"{row['fiscal_year']} {row['fiscal_period']} {row['period_end']} "
                    f"{row['ratio_category']} - {row['ratio_name']}: {display} ({row['quality_flag']})"
                )
    elif args.command == "export":
        out = Path(args.out) if args.out else Path("exports") / f"{args.ticker.upper()}_analysis.md"
        path = repo.export_markdown(args.ticker, out)
        print(f"Exported {path}")
    elif args.command == "serve":
        run_server(settings, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
