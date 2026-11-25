"""Validation tests for the curated canonical service dictionary (catalog_seed.json)."""

from app.normalization.catalog_loader import CatalogSeedItem, load_catalog_seed
from app.normalization.models import ServiceCategory
from app.normalization.text_utils import normalize_service_text


def test_catalog_seed_has_at_least_65_entries_and_all_four_categories() -> None:
    items = load_catalog_seed()
    assert len(items) >= 65
    categories = {item.category for item in items}
    assert categories == set(ServiceCategory)


def test_catalog_seed_codes_names_and_synonyms_are_unique_and_non_empty() -> None:
    items = load_catalog_seed()
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    seen_terms: dict[str, str] = {}

    for item in items:
        assert isinstance(item, CatalogSeedItem)
        assert item.code not in seen_codes, f"Duplicate code: {item.code}"
        seen_codes.add(item.code)

        norm_name = normalize_service_text(item.canonical_name)
        assert norm_name not in seen_names, f"Duplicate canonical_name: {item.canonical_name}"
        seen_names.add(norm_name)

        all_terms = [item.canonical_name, *item.synonyms]
        for term in all_terms:
            norm_term = normalize_service_text(term)
            assert norm_term, f"Empty normalized term in {item.code}: {term!r}"
            if norm_term in seen_terms:
                assert seen_terms[norm_term] == item.code, (
                    f"Ambiguous synonym '{term}' shared between "
                    f"{seen_terms[norm_term]} and {item.code}"
                )
            seen_terms[norm_term] = item.code


def test_catalog_seed_includes_tz_oak_synonyms() -> None:
    items = {item.code: item for item in load_catalog_seed()}
    oak = items["lab_oak"]
    assert oak.category == ServiceCategory.LAB
    norm_synonyms = {
        normalize_service_text(s) for s in [oak.canonical_name, *oak.synonyms]
    }
    for required in ("ОАК", "Общий анализ крови", "CBC", "Клинический анализ крови"):
        assert normalize_service_text(required) in norm_synonyms
