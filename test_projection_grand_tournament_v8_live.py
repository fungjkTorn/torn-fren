from services.projection_grand_tournament_v8_live_engine import _estimate


def test_v8_estimates():
    vals = [1, 2, 3, 4, 5]
    assert _estimate(vals, "median") == 3
    assert _estimate(vals, "mean") == 3
    assert _estimate(vals, "q25") == 2
    assert _estimate(vals, "q75") == 4
