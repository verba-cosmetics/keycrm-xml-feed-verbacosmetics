import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_feed as g


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.categories = [{"id": 1, "name": "Продукти"}, {"id": 2, "name": "Доставка"}]
        self.products = [
            {"id": 11, "category_id": 1, "attachments_data": ["https://example.com/cream.jpg"]},
            {"id": 12, "category_id": 1, "thumbnail_url": "https://example.com/coconut.jpg"},
            {"id": 13, "category_id": 1, "attachments_data": [{"url": "https://example.com/caramel.jpg"}]},
            {"id": 14, "category_id": 2},
        ]
        self.offers = [
            {"id": 4, "product_id": 11, "sku": "BHCCD", "price": 490},
            {"id": 3, "product_id": 12, "sku": "LGC", "price": 850},
            {"id": 1, "product_id": 13, "sku": "LGLECCPC", "price": 850},
            {"id": 9, "product_id": 14, "sku": "DELIVERY", "price": 50},
        ]
        self.stocks = [
            {"offer_id": 4, "quantity": 10, "in_reserve": 2},
            {"offer_id": 3, "quantity": 0},
            {"offer_id": 1, "quantity": 5},
        ]

    def test_eva_structure_and_stock(self):
        root = g.render_feed(self.categories, self.products, self.offers, self.stocks).getroot()
        self.assertEqual(root.tag, "yml_catalog")
        nodes = root.findall("./shop/offers/offer")
        self.assertEqual([n.attrib["id"] for n in nodes], ["4", "3", "1"])
        self.assertEqual([n.findtext("stock_quantity") for n in nodes], ["8", "0", "5"])
        self.assertEqual([n.attrib["available"] for n in nodes], ["true", "false", "true"])
        for node in nodes:
            for field in ("price", "stock_quantity", "currencyId", "categoryId", "picture", "vendor", "name_ua", "description_ua"):
                self.assertIsNotNone(node.find(field))
            self.assertGreaterEqual(len(node.findall("param")), 2)
            self.assertGreaterEqual(len(node.findtext("description_ua")), 30)
        ET.fromstring(ET.tostring(root, encoding="utf-8"))

    def test_missing_images_prevent_publish(self):
        self.products[0].pop("attachments_data")
        with self.assertRaisesRegex(ValueError, "No public HTTPS image"):
            g.render_feed(self.categories, self.products, self.offers, self.stocks)

    def test_missing_sku_prevents_accidental_deletion(self):
        self.offers.pop()
        self.offers.pop()
        with self.assertRaisesRegex(ValueError, "Catalog mismatch"):
            g.render_feed(self.categories, self.products, self.offers, self.stocks)


if __name__ == "__main__":
    unittest.main()
