  Official Torn API        YATA / Prometheus
         │                        │
         └───────────┬────────────┘
                      ▼
              StockProvider interface
           (YataProvider, PrometheusProvider)
                      │
                      ▼
              history_service.py (SQLite)
         — every ~30s, forever, per country/item —
                      │
      ┌───────────────┼───────────────┐
      ▼               ▼               ▼