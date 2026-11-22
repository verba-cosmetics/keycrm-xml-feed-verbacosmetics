import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
import generate_feed as g


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.categories = [{"id": 1, "name": "Продукти"}, {"id": 2, "name": "Доставка"}]
        self.products = [
            {"id": 11, "category_id": 1, "attachments_data": ["https://example.com/cream.jpg"], "properties": [{"name": "Тип засобу", "value": "Крем для рук"}, {"name": "Призначення", "value": "Догляд"}], "custom_fields": [{"uuid": "P_VOL", "value": "50 мл"}]},
            {"id": 12, "category_id": 1, "thumbnail_url": "https://example.com/coconut.jpg", "properties": [{"name": "Тип засобу", "value": "Блиск"}, {"name": "Об'єм", "value": "15 мл"}]},
            {"id": 13, "category_id": 1, "attachments_data": [{"url": "https://example.com/caramel.jpg"}], "properties": [{"name": "Тип засобу", "value": "Блиск"}, {"name": "Об'єм", "value": "15 мл"}]},
            {"id": 14, "category_id": 2},
        ]
        for item, kind, volume in zip(self.products[:3], ("Крем для рук", "Блиск для губ", "Блиск для губ"), (30, 15, 15)):
            item["custom_fields"] = [{"uuid": "CT_1014", "value": True},
                                     {"uuid": "CT_1015", "value": [kind]},
                                     {"uuid": "CT_1016", "value": volume}]
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


    def test_keycrm_plain_list_response(self):
        from unittest.mock import Mock
        response = Mock()
        response.json.return_value = [{"uuid": "volume", "name": "Об'єм"}]
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        fields = g.get_all(session, "custom-fields")
        self.assertEqual(fields, [{"uuid": "volume", "name": "Об'єм"}])
        self.assertEqual(session.get.call_count, 1)

    def test_keycrm_paginated_data_response(self):
        from unittest.mock import Mock
        response = Mock()
        response.json.return_value = {"data": [{"id": 1}], "meta": {"last_page": 1}}
        session = Mock()
        session.get.return_value = response
        self.assertEqual(g.get_all(session, "products"), [{"id": 1}])

    def test_eva_structure_and_stock(self):
        root = g.render_feed(self.categories, self.products, self.offers, self.stocks, [{"uuid": "P_VOL", "name": "Об\u0027єм"}]).getroot()
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
        self.assertEqual(root.find("./shop/offers/offer/param[@name=\"Об'єм\"]").text, "30")
        ET.fromstring(ET.tostring(root, encoding="utf-8"))

    def test_missing_keycrm_characteristics_keeps_product(self):
        self.products[0].pop("properties")
        self.products[0].pop("custom_fields")
        root = g.render_feed(self.categories, self.products, self.offers, self.stocks).getroot()
        cream = root.find("./shop/offers/offer[@id='4']")
        self.assertIsNotNone(cream)
        # Country of manufacture is published for Cashmere Dream even when
        # no custom CRM attributes exist. No other attributes are invented.
        self.assertEqual(
            [(p.get("name"), p.text) for p in cream.findall("param")],
            [("Країна виробництва", "Україна")],
        )
        self.assertEqual(cream.get("available"), "false")
        self.assertEqual(cream.findtext("stock_quantity"), "0")

    def test_direct_fields_and_plain_description(self):
        self.products[0]["description"] = "Крем для рук.\n**Переваги продукту**\n- Зволоження\nСклад: Aqua"
        self.products[0]["custom_fields"].append({"uuid": "TEST_ACTIVE", "value": ["Гліцерин", "Алантоїн"]})
        root = g.render_feed(self.categories, self.products, self.offers, self.stocks,
                             [{"uuid": "TEST_ACTIVE", "name": "Активний компонент"}]).getroot()
        cream = root.find("./shop/offers/offer[@id='4']")
        self.assertEqual(cream.findtext("description_ua"), self.products[0]["description"])
        self.assertEqual(cream.find("./param[@name='Вид']").text, "Крем для рук")
        self.assertEqual(cream.find("./param[@name='Активний компонент']").text, "Гліцерин, Алантоїн")
        self.assertIsNone(cream.find("./param[@name='Склад']"))

    def test_disabled_marketplace_and_missing_toggle(self):
        for value in (False, 0, "false", None):
            self.products[0]["custom_fields"][0]["value"] = value
            root = g.render_feed(self.categories, self.products, self.offers, self.stocks).getroot()
            cream = root.find("./shop/offers/offer[@id='4']")
            self.assertEqual(cream.get("available"), "false")
            self.assertEqual(cream.findtext("stock_quantity"), "0")

    def test_eva_html_and_rozetka_plain(self):
        from tempfile import TemporaryDirectory
        from generate_rozetka import convert
        self.products[0]["description"] = "Крем & догляд.\n**Переваги продукту**\n- М'якість"
        tree = g.render_feed(self.categories, self.products, self.offers, self.stocks)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eva.xml"
            g.write_eva_xml(tree, path)
            self.assertIn("<![CDATA[", path.read_text(encoding="utf-8"))
            eva = ET.parse(path).getroot()
            self.assertIn("<strong>Переваги продукту</strong>", eva.findtext("./shop/offers/offer/description_ua"))
            rz = convert(eva).getroot()
            self.assertIn("Крем & догляд.", rz.findtext("./shop/offers/offer/description_ua"))
            self.assertNotIn("<p>", rz.findtext("./shop/offers/offer/description_ua"))

    def test_eva_hand_care_catalog_parameters(self):
        root = g.render_feed(self.categories, self.products, self.offers, self.stocks).getroot()
        cream = root.find("./shop/offers/offer[@id='4']")
        self.assertEqual(cream.find("./param[@name='Вид']").text, "Крем для рук")
        self.assertEqual(cream.find("./param[@name=\"Об'єм\"]").text, "30")
        self.assertEqual(cream.find("./param[@name='Країна виробництва']").text, "Україна")
        for offer_id in ("3", "1"):
            gloss = root.find(f"./shop/offers/offer[@id='{offer_id}']")
            self.assertEqual(gloss.find("./param[@name=\"Об'єм\"]").text, "15")
            self.assertIsNone(gloss.find("./param[@name='Країна виробництва']"))

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
