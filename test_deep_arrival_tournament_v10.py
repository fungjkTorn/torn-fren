from services.deep_arrival_tournament_v10 import (
    DECISION_OFFSETS_MINUTES, WAIT_MINUTES, config_grid
)


def test_v10_grid_is_deep_but_bounded():
    c = list(config_grid())
    assert 150 <= len(c) <= 250
    assert any(x.family == "state" and x.feature_set == "timing" for x in c)
    assert any(x.family == "state" and x.feature_set == "demand" for x in c)
    assert any(x.family == "tod" for x in c)


def test_v10_decision_and_wait_grids():
    assert DECISION_OFFSETS_MINUTES[0] == 0
    assert DECISION_OFFSETS_MINUTES[-1] == 180
    assert WAIT_MINUTES[0] == 0
    assert WAIT_MINUTES[-1] == 240
