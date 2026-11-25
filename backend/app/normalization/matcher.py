"""Deterministic service name matcher: exact -> synonym -> category-isolated RapidFuzz."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.normalization.models import MatchMethod, ServiceCategory
from app.normalization.text_utils import map_category_hint, normalize_service_text

_DIGITS_RE = re.compile(r"\d+")
_MIN_FUZZY_LENGTH = 6


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """In-memory representation of a ServiceCatalog row for fast matching."""

    id: uuid.UUID
    code: str
    canonical_name: str
    category: ServiceCategory
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Outcome of matching a raw service name against the canonical dictionary."""

    service_id: uuid.UUID | None
    canonical_name: str | None
    category: ServiceCategory | None
    method: MatchMethod | None
    score: float
    suggested_service_id: uuid.UUID | None = None
    suggested_score: float | None = None

    @property
    def is_matched(self) -> bool:
        return self.service_id is not None


def _has_conflicting_numbers(norm_a: str, norm_b: str) -> bool:
    """Prevent fuzzy auto-merges when distinct numeric identifiers conflict (e.g. 071 vs 075)."""
    nums_a = set(_DIGITS_RE.findall(norm_a))
    nums_b = set(_DIGITS_RE.findall(norm_b))
    return bool(nums_a and nums_b and nums_a != nums_b)


class ServiceMatcher:
    """Three-tier deterministic matcher with category isolation and numeric-token guard."""

    def __init__(
        self,
        entries: Sequence[CatalogEntry],
        *,
        fuzzy_match_threshold: float = 86.0,
        fuzzy_suggestion_threshold: float = 60.0,
    ) -> None:
        if fuzzy_suggestion_threshold > fuzzy_match_threshold:
            raise ValueError("fuzzy_suggestion_threshold must be <= fuzzy_match_threshold")

        self.fuzzy_match_threshold = fuzzy_match_threshold
        self.fuzzy_suggestion_threshold = fuzzy_suggestion_threshold

        self._exact_by_category: dict[tuple[ServiceCategory, str], CatalogEntry] = {}
        self._exact_global: dict[str, CatalogEntry] = {}
        self._synonym_by_category: dict[tuple[ServiceCategory, str], CatalogEntry] = {}
        self._synonym_global: dict[str, CatalogEntry] = {}
        self._fuzzy_by_category: dict[ServiceCategory, list[tuple[str, CatalogEntry]]] = {
            cat: [] for cat in ServiceCategory
        }
        self._fuzzy_all: list[tuple[str, CatalogEntry]] = []

        for entry in entries:
            norm_canon = normalize_service_text(entry.canonical_name)
            if norm_canon:
                self._exact_by_category[(entry.category, norm_canon)] = entry
                self._exact_global.setdefault(norm_canon, entry)
                if len(norm_canon) >= _MIN_FUZZY_LENGTH:
                    self._fuzzy_by_category[entry.category].append((norm_canon, entry))
                    self._fuzzy_all.append((norm_canon, entry))

            for syn in entry.synonyms:
                norm_syn = normalize_service_text(syn)
                if not norm_syn:
                    continue
                self._synonym_by_category[(entry.category, norm_syn)] = entry
                self._synonym_global.setdefault(norm_syn, entry)
                if len(norm_syn) >= _MIN_FUZZY_LENGTH:
                    self._fuzzy_by_category[entry.category].append((norm_syn, entry))
                    self._fuzzy_all.append((norm_syn, entry))

    def match(self, raw_name: str, *, category_hint: str | None = None) -> MatchResult:
        """Match a raw service string using exact -> synonym -> category-isolated fuzzy tiers."""
        norm_query = normalize_service_text(raw_name)
        if not norm_query:
            return MatchResult(
                service_id=None,
                canonical_name=None,
                category=None,
                method=None,
                score=0.0,
            )

        hinted_cat = map_category_hint(category_hint)

        # Tier 1: exact canonical name (prefer hinted category, then global)
        exact_entry = (
            self._exact_by_category.get((hinted_cat, norm_query))
            if hinted_cat is not None
            else None
        ) or self._exact_global.get(norm_query)
        if exact_entry is not None:
            return MatchResult(
                service_id=exact_entry.id,
                canonical_name=exact_entry.canonical_name,
                category=exact_entry.category,
                method=MatchMethod.EXACT,
                score=100.0,
            )

        # Tier 2: exact synonym match (prefer hinted category, then global)
        syn_entry = (
            self._synonym_by_category.get((hinted_cat, norm_query))
            if hinted_cat is not None
            else None
        ) or self._synonym_global.get(norm_query)
        if syn_entry is not None:
            return MatchResult(
                service_id=syn_entry.id,
                canonical_name=syn_entry.canonical_name,
                category=syn_entry.category,
                method=MatchMethod.SYNONYM,
                score=100.0,
            )

        # Guard: very short abbreviations (< 6 chars) must match via exact/synonym only
        if len(norm_query) < _MIN_FUZZY_LENGTH:
            return MatchResult(
                service_id=None,
                canonical_name=None,
                category=None,
                method=None,
                score=0.0,
            )

        # Tier 3: category-isolated RapidFuzz matching
        candidates = (
            self._fuzzy_by_category[hinted_cat] if hinted_cat is not None else self._fuzzy_all
        )
        best_entry: CatalogEntry | None = None
        best_score = 0.0

        for candidate_text, entry in candidates:
            if _has_conflicting_numbers(norm_query, candidate_text):
                continue
            score = float(fuzz.token_sort_ratio(norm_query, candidate_text))
            if score > best_score:
                best_score = score
                best_entry = entry

        rounded = round(best_score, 2)
        if best_entry is not None and rounded >= self.fuzzy_match_threshold:
            return MatchResult(
                service_id=best_entry.id,
                canonical_name=best_entry.canonical_name,
                category=best_entry.category,
                method=MatchMethod.FUZZY,
                score=rounded,
            )

        if best_entry is not None and rounded >= self.fuzzy_suggestion_threshold:
            return MatchResult(
                service_id=None,
                canonical_name=None,
                category=None,
                method=None,
                score=rounded,
                suggested_service_id=best_entry.id,
                suggested_score=rounded,
            )

        return MatchResult(
            service_id=None,
            canonical_name=None,
            category=None,
            method=None,
            score=rounded,
        )
