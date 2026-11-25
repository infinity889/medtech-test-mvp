"""Unit tests for deterministic ServiceMatcher (exact, synonym, category-isolated RapidFuzz)."""

import uuid

import pytest

from app.normalization.catalog_loader import load_catalog_seed
from app.normalization.matcher import CatalogEntry, ServiceMatcher
from app.normalization.models import MatchMethod, ServiceCategory


def _build_matcher_from_seed() -> tuple[ServiceMatcher, dict[str, uuid.UUID]]:
    seed_items = load_catalog_seed()
    entries: list[CatalogEntry] = []
    code_to_id: dict[str, uuid.UUID] = {}
    for item in seed_items:
        sid = uuid.uuid5(uuid.NAMESPACE_DNS, f"medprice.{item.code}")
        code_to_id[item.code] = sid
        entries.append(
            CatalogEntry(
                id=sid,
                code=item.code,
                canonical_name=item.canonical_name,
                category=item.category,
                synonyms=tuple(item.synonyms),
            )
        )
    return ServiceMatcher(entries), code_to_id


@pytest.mark.parametrize(
    "raw_name",
    [
        "ОАК",
        "Общий анализ крови",
        "CBC",
        "Клинический анализ крови",
        "Общий анализ крови (ОАК без СОЭ)",
        (
            "Клинический анализ крови с лейкоцитарной формулой* и измерением "
            "скорости оседания эритроцитов (ОАК + СОЭ)"
        ),
        "Кровь. Общий анализ (ОАК: эритроциты, гемоглобин, лейкоциты, тромбоциты, СОЭ)",
    ],
)
def test_matcher_unifies_all_oak_variants_to_lab_oak(raw_name: str) -> None:
    matcher, ids = _build_matcher_from_seed()
    result = matcher.match(raw_name, category_hint="лаборатория")
    assert result.is_matched
    assert result.service_id == ids["lab_oak"]
    assert result.method in {MatchMethod.EXACT, MatchMethod.SYNONYM}
    assert result.score == 100.0


def test_matcher_exact_synonym_and_fuzzy_tiers() -> None:
    matcher, ids = _build_matcher_from_seed()

    exact = matcher.match("Ферритин", category_hint="лаборатория")
    assert exact.is_matched
    assert exact.service_id == ids["lab_ferritin"]
    assert exact.method == MatchMethod.EXACT
    assert exact.score == 100.0

    syn = matcher.match("Терапевт", category_hint="приём врача")
    assert syn.is_matched
    assert syn.service_id == ids["doc_terapevt"]
    assert syn.method == MatchMethod.SYNONYM

    fuzzy = matcher.match("УЗИ органов брюшной полости", category_hint="диагностика")
    assert fuzzy.is_matched
    assert fuzzy.service_id == ids["diag_uzi_obp"]

    fuzzy_typo = matcher.match("УЗИ щитовидной желез", category_hint="диагностика")
    assert fuzzy_typo.is_matched
    assert fuzzy_typo.service_id == ids["diag_uzi_thyroid"]
    assert fuzzy_typo.method == MatchMethod.FUZZY
    assert fuzzy_typo.score >= 86.0


def test_matcher_enforces_category_isolation_on_fuzzy() -> None:
    matcher, _ = _build_matcher_from_seed()
    # Close in wording to lab_esr, but explicitly tagged as doctor visit -> must NOT fuzzy-match lab
    result = matcher.match(
        "Измерение скорости оседания эритроцитов анализатор",
        category_hint="приём врача",
    )
    assert not result.is_matched


@pytest.mark.parametrize(
    ("raw_name", "hint"),
    [
        ("Т3", "лаборатория"),
        ("Т4", "лаборатория"),
        ("Витамин B6", "лаборатория"),
        ("Справка 071/у (в лагерь)", "процедура"),
        ("Справка 037 детям", "процедура"),
    ],
)
def test_matcher_prevents_false_acronym_and_numeric_merges(raw_name: str, hint: str) -> None:
    matcher, _ = _build_matcher_from_seed()
    result = matcher.match(raw_name, category_hint=hint)
    assert not result.is_matched


def test_matcher_routes_unmatched_with_and_without_suggestion() -> None:
    matcher, ids = _build_matcher_from_seed()

    near = matcher.match("УЗИ органов малого таза трансвагинальное 3D", category_hint="диагностика")
    assert not near.is_matched
    assert near.suggested_service_id == ids["diag_uzi_pelvis"]
    assert near.suggested_score is not None
    assert 60.0 <= near.suggested_score < 86.0

    unknown = matcher.match("Экзотическая процедура XYZ-999", category_hint="процедура")
    assert not unknown.is_matched
    assert unknown.suggested_service_id is None
    assert unknown.suggested_score is None


def test_matcher_resolves_cross_category_exact_synonym_from_aggregator() -> None:
    """DOQ.kz lists СМАД / Кольпоскопия under doctor pages; exact/synonym match still finds them."""
    matcher, ids = _build_matcher_from_seed()
    res = matcher.match(
        "Суточное мониторирование артериального давления (СМАД)",
        category_hint="приём врача",
    )
    assert res.is_matched
    assert res.service_id == ids["diag_smad"]
    assert res.category == ServiceCategory.DIAGNOSTICS
