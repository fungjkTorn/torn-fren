from services.projection_grand_tournament_v7_engine import (
    _estimate, GrandConfig
)


def test_estimate_recent_methods():
    vals = [1, 2, 3, 4, 5]
    assert _estimate(vals, "last1") == 5
    assert _estimate(vals, "last2_mean") == 4.5
    assert _estimate(vals, "last3_mean") == 4
    assert _estimate(vals, "median") == 3


def test_config_name_is_stable():
    c = GrandConfig("median", 40, 3.0, "last1", 0.25, "recent10")
    assert "h=median" in c.name
    assert "f=0.25" in c.name
