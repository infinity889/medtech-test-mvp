"""Offline E2E tests covering all 3 built-in KZ adapters through IngestionService and CLI."""

from pathlib import Path

import httpx
import respx
from sqlalchemy import delete

from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.ingestion.adapters.doq import DoqAdapter
from app.ingestion.adapters.invivo import InvivoAdapter
from app.ingestion.adapters.kdlolymp import KdlOlympAdapter
from app.ingestion.adapters.registry import AdapterRegistry, default_registry
from app.ingestion.cli import run_cli
from app.ingestion.http_client import PoliteHttpClient
from app.ingestion.models import RawServiceRecord, ScrapeError, ScrapeRun, ScrapeStatus
from app.ingestion.runner import IngestionRunner
from app.ingestion.service import IngestionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_default_registry_contains_all_three_approved_kz_sources() -> None:
    ids = {src.source_id for src in default_registry.list_all()}
    assert {"kdlolymp", "invivo", "doq"}.issubset(ids)


@respx.mock
async def test_e2e_three_adapters_ingest_and_rerun_has_zero_duplicates() -> None:
    respx.get("https://kdlolymp.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://kdlolymp.kz/pricelist/almaty").mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES_DIR / "kdlolymp_pricelist_almaty.html").read_text(encoding="utf-8"),
        )
    )
    respx.get("https://invivo.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://invivo.kz/ru/almaty/analyzes/obshcheklinicheskie-issledovaniia/").mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES_DIR / "invivo_category_almaty.html").read_text(encoding="utf-8"),
        )
    )
    respx.get("https://doq.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://doq.kz/doctors/almaty/terapevt").mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES_DIR / "doq_almaty_terapevt.html").read_text(encoding="utf-8"),
        )
    )

    engine = create_db_engine(Settings().database_url)
    session_factory = create_session_factory(engine)
    source_ids = ["kdlolymp", "invivo", "doq"]

    async def no_sleep(_: float) -> None:
        return None

    registry = AdapterRegistry()
    registry.register(KdlOlympAdapter(cities=[("almaty", "Алматы")]))
    registry.register(
        InvivoAdapter(
            cities=[("almaty", "Алматы")],
            category_slugs=["obshcheklinicheskie-issledovaniia"],
        )
    )
    registry.register(
        DoqAdapter(
            cities=[("almaty", "Алматы")],
            listing_slugs=[("terapevt", "приём врача")],
        )
    )

    try:
        runner = IngestionRunner(
            session_factory=session_factory,
            registry=registry,
            http_client_factory=lambda: PoliteHttpClient(
                min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep
            ),
        )
        first = await runner.run_sources()
        assert len(first) == 3
        assert all(r.status == ScrapeStatus.SUCCESS for r in first)
        assert all(r.records_inserted == 2 for r in first)

        second = await runner.run_sources()
        assert len(second) == 3
        assert all(r.status == ScrapeStatus.SUCCESS for r in second)
        assert all(r.records_inserted == 0 for r in second)
        assert all(r.records_updated == 2 for r in second)

        service = IngestionService(session_factory=session_factory, registry=registry)
        all_rows = [rec for batch in service.iter_raw_records() for rec in batch]
        assert len(all_rows) == 6
        assert {r.source_id for r in all_rows} == set(source_ids)

        assert run_cli(["purge-expired", "--retention-days", "90"], service=service) == 0
    finally:
        with session_factory() as session:
            session.execute(delete(ScrapeError).where(ScrapeError.source_id.in_(source_ids)))
            session.execute(
                delete(RawServiceRecord).where(RawServiceRecord.source_id.in_(source_ids))
            )
            session.execute(delete(ScrapeRun).where(ScrapeRun.source_id.in_(source_ids)))
            session.commit()
        engine.dispose()
