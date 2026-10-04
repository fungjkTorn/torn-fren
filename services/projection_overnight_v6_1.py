import services.projection_overnight_v6 as base
from services.projection_engine_v6_1 import (
    DECLARATION_THRESHOLDS,
    selective_rank_key,
)

# Patch the V6 tournament's selection globals without duplicating the full runner.
base.DECLARATION_THRESHOLDS = DECLARATION_THRESHOLDS
base.selective_rank_key = selective_rank_key

if __name__ == "__main__":
    base.main()
