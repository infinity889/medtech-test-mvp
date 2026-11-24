"""Command-line interface for running ingestion jobs manually or from cron."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from app.ingestion.service import IngestionService, create_default_ingestion_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion.cli",
        description="MedServicePrice.kz ingestion CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-sources", help="List registered data source adapters")

    run_cmd = sub.add_parser("run", help="Run one or all source adapters")
    run_cmd.add_argument(
        "--source",
        default="all",
        help="Adapter source_id or 'all' (comma-separated allowed)",
    )
    run_cmd.add_argument(
        "--triggered-by",
        choices=["manual", "cron"],
        default="manual",
        help="Trigger origin recorded in scrape_runs",
    )
    run_cmd.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max records per adapter (useful for smoke runs)",
    )

    purge_cmd = sub.add_parser(
        "purge-expired", help="Delete raw records older than retention window (>= 90 days)"
    )
    purge_cmd.add_argument("--retention-days", type=int, default=90)

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    service: IngestionService | None = None,
) -> int:
    """Execute ingestion CLI and return process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    svc = service or create_default_ingestion_service()

    if args.command == "list-sources":
        payload = [src.model_dump() for src in svc.list_sources()]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run":
        source_ids: list[str] | None = (
            None
            if args.source.strip().lower() == "all"
            else [s.strip() for s in args.source.split(",") if s.strip()]
        )
        runs = asyncio.run(
            svc.trigger_run(
                source_ids=source_ids,
                triggered_by=args.triggered_by,
                limit=args.limit,
            )
        )
        output = [r.model_dump(mode="json") for r in runs]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if args.command == "purge-expired":
        deleted = svc.purge_expired_raw_records(retention_days=args.retention_days)
        print(json.dumps({"deleted_records": deleted, "retention_days": args.retention_days}))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
