"""Loader and validator for the version-controlled canonical service catalog seed."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.normalization.models import ServiceCategory

DEFAULT_SEED_PATH = Path(__file__).parent / "data" / "catalog_seed.json"


class CatalogSeedItem(BaseModel):
    """Single canonical service definition in catalog_seed.json."""

    code: str = Field(min_length=2, max_length=64)
    canonical_name: str = Field(min_length=2, max_length=256)
    category: ServiceCategory
    synonyms: list[str] = Field(default_factory=list)
    description: str | None = None


def load_catalog_seed(path: Path | None = None) -> list[CatalogSeedItem]:
    """Load and validate canonical service entries from JSON."""
    seed_path = path or DEFAULT_SEED_PATH
    raw_items = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        raise ValueError(f"Catalog seed at {seed_path} must be a JSON array")
    return [CatalogSeedItem.model_validate(item) for item in raw_items]
