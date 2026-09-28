from modules.arbitrage import ArbitrageOpportunity, BazaarListing, BuyOffer
import os
import unittest
from unittest.mock import patch

from services.arbitrage_live import (
    ForeignItem,
    _anomaly_labels_for_item,
    build_arbitrage_report,
    build_trader_finder,
    fetch_torn_item_market,
    fetch_tornexchange_buy_offers,
    fetch_tornw3b_bazaar,
    fetch_tornw3b_buy_offers,
    parse_tornexchange_listings_html,
    parse_weav3r_bazaar_html,
)


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(self.payload)


class LiveArbitrageParserTests(unittest.TestCase):
    def test_parse_weav3r_bazaar_table(self):
        html = """
        <html><body>
          <table>
            <thead><tr>
              <th>Seller</th><th>Quantity</th><th>Price / Total Value</th><th>Last Checked</th>
            </tr></thead>
            <tbody>
              <tr>
                <td><a href="https://www.torn.com/profiles.php?XID=4222297">S_G [4222297]</a></td>
                <td>1</td>
                <td>$109,999 (1%) $109,999</td>
                <td>1 min ago</td>
              </tr>
              <tr>
                <td><a href="https://www.torn.com/profiles.php?XID=3539339">UnmatchedGamer [3539339]</a></td>
                <td>9</td>
                <td>$109,999 (1%) $989,991</td>
                <td>1 min ago</td>
              </tr>
            </tbody>
          </table>
        </body></html>
        """

        rows = parse_weav3r_bazaar_html(
            html,
            item_id="1502",
            item_name="Basalt Point",
            observed_at=123.0,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].item_id, "1502")
        self.assertEqual(rows[0].unit_price, 109_999)
        self.assertEqual(rows[0].quantity, 1)
        self.assertEqual(rows[0].seller_name, "S_G")
        self.assertEqual(rows[0].seller_id, "4222297")
        self.assertEqual(rows[1].quantity, 9)

    def test_parse_tornexchange_listing_card(self):
        html = """
        <html><body>
          <div class="listing-card">
            <div>Trader One [123456]</div>
            <div>Buy Price $134,000</div>
            <div>Current market: $108,829</div>
            <div>Artifact: Basalt Point</div>
            <a href="/prices/Trader-One/">Price List</a>
          </div>
        </body></html>
        """

        rows = parse_tornexchange_listings_html(
            html,
            item_id="1502",
            item_name="Basalt Point",
            observed_at=123.0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_price, 134_000)
        self.assertEqual(rows[0].buyer_name, "Trader One")
        self.assertEqual(rows[0].buyer_id, "123456")
        self.assertEqual(rows[0].url, "https://www.tornexchange.com/prices/Trader-One/")

    def test_fetch_tornw3b_bazaar_json(self):
        item = ForeignItem("1502", "Basalt Point", ("Argentina",), (50_000,))
        session = _FakeSession(
            {
                "item_id": 1502,
                "item_name": "Basalt Point",
                "listings": [
                    {
                        "player_id": 4222297,
                        "player_name": "S_G",
                        "quantity": 7,
                        "price": 109999,
                        "last_checked": 1_700_000_000,
                    }
                ],
            }
        )

        rows = fetch_tornw3b_bazaar(item, session=session)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_price, 109_999)
        self.assertEqual(rows[0].quantity, 7)
        self.assertEqual(rows[0].source, "tornw3b_bazaar")
        self.assertEqual(rows[0].seller_id, "4222297")

    def test_fetch_tornw3b_trader_json(self):
        item = ForeignItem("1502", "Basalt Point", ("Argentina",), (50_000,))
        session = _FakeSession(
            {
                "generated_at": 1_700_000_000,
                "traders": [
                    {
                        "player_id": 123456,
                        "player_name": "Trader One",
                        "price": 134000,
                        "last_trade": 1_699_999_999,
                    }
                ],
            }
        )

        rows = fetch_tornw3b_buy_offers(item, session=session)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_price, 134_000)
        self.assertEqual(rows[0].buyer_name, "Trader One")
        self.assertEqual(rows[0].source, "tornw3b_trader")
        self.assertTrue(rows[0].url.endswith("/pricelist/123456"))

    def test_fetch_official_item_market_json(self):
        item = ForeignItem("1502", "Basalt Point", ("Argentina",), (50_000,))
        session = _FakeSession(
            {
                "itemmarket": {
                    "item": {"id": 1502, "name": "Basalt Point"},
                    "listings": [
                        {"price": 108000, "amount": 14},
                        {"price": 109500, "amount": 3},
                    ],
                }
            }
        )

        with patch.dict(os.environ, {"TORN_API_KEY": "test-key"}):
            rows = fetch_torn_item_market(item, session=session)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].unit_price, 108_000)
        self.assertEqual(rows[0].quantity, 14)
        self.assertEqual(rows[0].source, "torn_item_market")

    def test_tornexchange_listings_page_beats_api_style_price(self):
        item = ForeignItem("1488", "Meteorite Fragment", ("Argentina",), (400_904,))
        html = """
        <html><body>
          <div class="listing-card">
            <div>EVETINE [2231549]</div>
            <div>$505,000</div>
            <div>Current market: $458,392</div>
            <div>Artifact: Meteorite Fragment</div>
            <a href="/prices/EVETINE/">Price List</a>
            <a href="#">Trade Now</a>
          </div>
          <div class="listing-card">
            <div>Qfiffle [2557282]</div>
            <div>$460,944</div>
            <div>Current market: $458,392</div>
            <div>Artifact: Meteorite Fragment</div>
            <a href="/prices/Qfiffle/">Price List</a>
            <a href="#">Trade Now</a>
          </div>
        </body></html>
        """

        class ListingsSession:
            def get(self, url, **kwargs):
                return _FakeResponse(text=html)

        with patch("services.arbitrage_live._read_te_cache", return_value=None), \
             patch("services.arbitrage_live._write_te_cache") as write_cache, \
             patch("services.arbitrage_live._wait_for_tornexchange_listings_slot"):
            rows = fetch_tornexchange_buy_offers(
                item,
                session=ListingsSession(),
                force=True,
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].buyer_name, "EVETINE")
        self.assertEqual(rows[0].unit_price, 505_000)
        write_cache.assert_called_once()
        self.assertEqual(write_cache.call_args.kwargs["price"], 505_000)

    def test_tornexchange_rejects_fuzzy_similar_item_names(self):
        html = """
        <html><body>
          <div class="listing-card">
            <div>Juki11 [4194497]</div>
            <div>$15,345,000,000</div>
            <div>Current market: $15,500,000,000</div>
            <div>Primary: Gold Plated AK-47</div>
            <a href="/prices/Juki11/">Price List</a>
            <a href="#">Trade Now</a>
          </div>
          <div class="listing-card">
            <div>Trader Axe [123456]</div>
            <div>$5,841,000,000</div>
            <div>Current market: $5,900,000,000</div>
            <div>Melee: Dual Axes</div>
            <a href="/prices/Trader-Axe/">Price List</a>
            <a href="#">Trade Now</a>
          </div>
        </body></html>
        """

        ak_rows = parse_tornexchange_listings_html(
            html,
            item_id="26",
            item_name="AK-47",
            observed_at=123.0,
        )
        axe_rows = parse_tornexchange_listings_html(
            html,
            item_id="8",
            item_name="Axe",
            observed_at=123.0,
        )

        self.assertEqual(ak_rows, [])
        self.assertEqual(axe_rows, [])

    def test_tornexchange_ignores_generic_prices_navigation_link(self):
        html = """
        <html><body>
          <div>
            <a href="/prices/">Price List</a>
            <div>$999,999</div>
            <div>Artifact: Basalt Point</div>
          </div>
          <div class="listing-card">
            <div>Shinsengumi [2097185]</div>
            <div>$134,000</div>
            <div>Current market: $108,829</div>
            <div>Artifact: Basalt Point</div>
            <a href="/prices/Shinsengumi/">Price List</a>
            <a href="#">Trade Now</a>
          </div>
        </body></html>
        """

        rows = parse_tornexchange_listings_html(
            html,
            item_id="1502",
            item_name="Basalt Point",
            observed_at=123.0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].buyer_name, "Shinsengumi")
        self.assertEqual(rows[0].unit_price, 134_000)
        self.assertEqual(
            rows[0].url,
            "https://www.tornexchange.com/prices/Shinsengumi/",
        )

    def test_tornexchange_rejects_more_fuzzy_item_variants(self):
        cases = [
            ("Lighter", "Enhancer: Windproof Lighter", 6_774_104),
            ("Samurai Sword", "Melee: Dual Samurai Swords", 1_657_837_500),
            ("Grenade", "Temporary: Concussion Grenade", 3_100_000),
            ("Paper Weight", "Other: Spooky Paper Weight", 3_462_920),
        ]

        for requested, displayed, price in cases:
            with self.subTest(requested=requested):
                html = f"""
                <html><body>
                  <div class="listing-card">
                    <div>Trader [123456]</div>
                    <div>${price:,}</div>
                    <div>Current market: ${price:,}</div>
                    <div>{displayed}</div>
                    <a href="/prices/Trader/">Price List</a>
                    <a href="#">Trade Now</a>
                  </div>
                </body></html>
                """
                rows = parse_tornexchange_listings_html(
                    html,
                    item_id="1",
                    item_name=requested,
                    observed_at=123.0,
                )
                self.assertEqual(rows, [])

    def test_anomaly_labels_do_not_hide_extreme_offer(self):
        opportunity = ArbitrageOpportunity(
            item_name="Fire Hydrant",
            buyer_name="Trader A",
            buyer_source="tornw3b_trader",
            buyer_price=2_400_000,
            buyer_url=None,
            item_id="410",
            quantity=100,
            total_cost=1_600_000,
            total_revenue=240_000_000,
            total_profit=238_400_000,
            average_buy_price=16_000,
            average_profit_per_item=2_384_000,
            roi=149.0,
            cheapest_buy_price=15_000,
            highest_accepted_buy_price=17_000,
            seller_count=20,
            listing_count=20,
            buy_sources=("tornw3b_bazaar",),
            buy_source_quantities={"tornw3b_bazaar": 100},
            buy_source_costs={"tornw3b_bazaar": 1_600_000},
        )
        offers = [
            BuyOffer("Fire Hydrant", 2_400_000, "tornw3b_trader", "Trader A", item_id="410"),
            BuyOffer("Fire Hydrant", 20_000, "tornw3b_trader", "Trader B", item_id="410"),
        ]

        labels, meta = _anomaly_labels_for_item(opportunity, offers)

        self.assertIn("Extreme spread — verify trader", labels)
        self.assertIn("Top buyer far above next bid", labels)
        self.assertEqual(meta["second_best_buyer_price"], 20_000)

    def test_report_filters_buy_and_buyer_sources(self):
        snapshot = {
            "timestamp": 123.0,
            "refreshing": False,
            "catalog": [
                ForeignItem("1", "Item X", ("Argentina",), (50,)),
                ForeignItem("2", "Item Y", ("Japan",), (50,)),
            ],
            "listings": [
                BazaarListing("Item X", 100, 2, "tornw3b_bazaar", item_id="1"),
                BazaarListing("Item X", 90, 3, "torn_item_market", item_id="1"),
                BazaarListing("Item Y", 80, 4, "tornw3b_bazaar", item_id="2"),
            ],
            "offers": [
                BuyOffer("Item X", 150, "tornw3b_trader", "W3B Buyer", item_id="1"),
                BuyOffer("Item X", 170, "torn_exchange", "TE Buyer", item_id="1"),
                BuyOffer("Item Y", 140, "torn_exchange", "TE Y", item_id="2"),
            ],
            "errors": [],
        }

        with patch("services.arbitrage_live.get_source_snapshot", return_value=snapshot):
            report = build_arbitrage_report(
                min_profit_per_item=20,
                buy_source="item_market",
                buyer_source="torn_exchange",
                country="Argentina",
            )

        self.assertEqual(report["opportunity_count"], 1)
        row = report["opportunities"][0]
        self.assertEqual(row["item_name"], "Item X")
        self.assertEqual(row["buyer_name"], "TE Buyer")
        self.assertEqual(row["quantity"], 3)
        self.assertEqual(row["buy_source_quantities"], {"torn_item_market": 3})

    def test_trader_finder_ranks_and_deduplicates_buyers(self):
        snapshot = {
            "timestamp": 123.0,
            "refreshing": False,
            "catalog": [ForeignItem("1", "Item X", ("Argentina",), (50,))],
            "listings": [],
            "offers": [
                BuyOffer("Item X", 150, "tornw3b_trader", "Buyer A", item_id="1", buyer_id="10"),
                BuyOffer("Item X", 160, "tornw3b_trader", "Buyer A", item_id="1", buyer_id="10"),
                BuyOffer("Item X", 170, "torn_exchange", "Buyer B", item_id="1", buyer_id="20"),
            ],
            "errors": [],
        }

        with patch("services.arbitrage_live.get_source_snapshot", return_value=snapshot):
            result = build_trader_finder("Item X")

        self.assertTrue(result["found"])
        self.assertEqual(result["buyer_count"], 2)
        self.assertEqual(result["buyers"][0]["buyer_name"], "Buyer B")
        self.assertEqual(result["buyers"][0]["price"], 170)
        self.assertEqual(result["buyers"][1]["buyer_name"], "Buyer A")
        self.assertEqual(result["buyers"][1]["price"], 160)

        with patch("services.arbitrage_live.get_source_snapshot", return_value=snapshot):
            result = build_trader_finder("Item X", buyer_source="torn_exchange")

        self.assertEqual(result["buyer_count"], 1)
        self.assertEqual(result["buyers"][0]["buyer_name"], "Buyer B")


if __name__ == "__main__":
    unittest.main()
