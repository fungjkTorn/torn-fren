from services.overnight_arrival_tournament_v10_other_items import (
    CORE_ITEMS, COUNTRIES
)


def test_core_exclusion_contains_benchmarks():
    assert ("jap", "Xanax") in CORE_ITEMS
    assert ("uni", "Xanax") in CORE_ITEMS
    assert ("can", "Xanax") in CORE_ITEMS
    assert ("arg", "Monkey Plushie") in CORE_ITEMS
    assert ("jap", "Cherry Blossom") in CORE_ITEMS


def test_all_foreign_countries_present():
    assert set(COUNTRIES) == {
        "mex", "cay", "can", "haw", "uni", "arg",
        "swi", "jap", "chi", "uae", "sou",
    }
