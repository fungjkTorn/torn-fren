import unittest

from services.arbitrage_live import (
    parse_tornexchange_listings_html,
    parse_weav3r_bazaar_html,
)


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


if __name__ == "__main__":
    unittest.main()
