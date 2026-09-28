import os
import unittest
from unittest.mock import patch

from services.arbitrage_live import (
    ForeignItem,
    fetch_torn_item_market,
    fetch_tornw3b_bazaar,
    fetch_tornw3b_buy_offers,
    parse_tornexchange_listings_html,
    parse_weav3r_bazaar_html,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

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
            <h3>Basalt Point</h3>
            <div>Trader One [123456]</div>
            <div>Buy Price $134,000</div>
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


if __name__ == "__main__":
    unittest.main()
