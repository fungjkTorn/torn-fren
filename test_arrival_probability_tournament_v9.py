from services.arrival_probability_tournament_v9 import (
    ProbabilityConfig,
    _base_weights,
    config_grid,
)


def test_v9_grid_is_bounded():
    configs = list(config_grid())
    assert 20 <= len(configs) <= 50
    assert any(c.family == "recent_uniform" and c.lookback == 10 for c in configs)
    assert any(c.family == "recent_state" for c in configs)


def test_exponential_weights_favor_recent():
    c = ProbabilityConfig("recent_exponential", 30, 0, half_life=5)
    w = _base_weights(5, c)
    assert w[-1] > w[0]
