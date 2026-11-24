"""Periodic scheduler for automated daily ingestion runs."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.ingestion.service import IngestionService


def create_ingestion_scheduler(
    service: IngestionService,
    *,
    interval_hours: int = 24,
) -> AsyncIOScheduler:
    """Create an AsyncIOScheduler with a daily job running all enabled source adapters."""
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")

    scheduler = AsyncIOScheduler(timezone="UTC")

    async def _scheduled_job() -> None:
        await service.trigger_run(source_ids=None, triggered_by="cron")

    scheduler.add_job(
        _scheduled_job,
        trigger="interval",
        hours=interval_hours,
        id="daily_ingestion_run",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
