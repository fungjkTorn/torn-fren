import os
import unittest
from unittest.mock import patch

from services.arbitrage_live import (
    ForeignItem,
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


if __name__ == "__main__":
    unittest.main()
