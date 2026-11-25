"""Command-line interface for catalog seeding, normalization runs, and staleness refresh."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from app.normalization.service import NormalizationService, create_default_normalization_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.normalization.cli",
        description="MedServicePrice.kz normalization CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "seed-catalog",
        help="Idempotently seed canonical services from catalog_seed.json",
    )

    run_cmd = sub.add_parser("run", help="Normalize raw records into clinics, offers, and history")
    run_cmd.add_argument(
        "--source",
        default=None,
        help="Optional source_id filter (default: all sources)",
    )

    stale_cmd = sub.add_parser(
        "refresh-stale", help="Mark service_offers older than max-age-days as inactive"
    )
    stale_cmd.add_argument("--max-age-days", type=int, default=30)

    sub.add_parser("stats", help="Print counts across normalized tables")
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    service: NormalizationService | None = None,
) -> int:
    """Execute normalization CLI and return process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    owns_service = service is None
    svc = service or create_default_normalization_service()

    try:
        if args.command == "seed-catalog":
            summary = svc.seed_catalog()
            print(json.dumps(summary.model_dump(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "run":
            run_summary = svc.run_normalization(source_id=args.source)
            print(json.dumps(run_summary.model_dump(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "refresh-stale":
            deactivated = svc.refresh_stale_offers(max_age_days=args.max_age_days)
            print(
                json.dumps(
                    {"deactivated_offers": deactivated, "max_age_days": args.max_age_days},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "stats":
            print(json.dumps(svc.get_stats(), ensure_ascii=False, indent=2))
            return 0

        parser.error(f"Unknown command: {args.command}")
        return 2
    finally:
        if owns_service:
            svc.close()


if __name__ == "__main__":
    raise SystemExit(run_cli())
