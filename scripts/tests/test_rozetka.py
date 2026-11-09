import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))

import unittest
import xml.etree.ElementTree as ET

from generate_rozetka import convert


SOURCE = """<yml_catalog date="2026-11-05 17:55"><shop><name>Verba Cosmetics</name>
<currencies><currency id="UAH" rate="1"/></currencies>
<categories><category id="101">Креми для рук</category><category id="102">Блиски для губ</category></categories>
<offers>
<offer id="4" available="true"><price>490</price><currencyId>UAH</currencyId><categoryId>101</categoryId>
<picture>https://example.com/cream.png</picture><stock_quantity>6000</stock_quantity><vendor>Verba Cosmetics</vendor>
<name_ua>Крем для рук Cashmere Dream</name_ua><description_ua>Бар'єрний крем для щоденного догляду за шкірою рук.</description_ua><param name="Тип">Крем</param></offer>
<offer id="3" available="false"><price>850</price><currencyId>UAH</currencyId><categoryId>102</categoryId>
<picture>https://example.com/coconut.png</picture><stock_quantity>0</stock_quantity><vendor>Verba Cosmetics</vendor>
<name_ua>Блиск Coconut</name_ua><description_ua>Блиск для декоративного макіяжу губ.</description_ua><param name="Тип">Блиск</param></offer>
<offer id="1" available="true"><price>850</price><currencyId>UAH</currencyId><categoryId>102</categoryId>
<picture>https://example.com/caramel.png</picture><stock_quantity>100</stock_quantity><vendor>Verba Cosmetics</vendor>
<name_ua>Блиск Crystal Caramel</name_ua><description_ua>Блиск для декоративного макіяжу губ.</description_ua><param name="Тип">Блиск</param></offer>
</offers></shop></yml_catalog>"""


class RozetkaTests(unittest.TestCase):
    def test_required_fields_and_same_ids(self):
        source = ET.fromstring(SOURCE)
        result = convert(source).getroot()
        self.assertEqual([o.get("id") for o in result.findall("./shop/offers/offer")], ["4", "3", "1"])
        self.assertEqual(len(result.findall("./shop/offers/offer")), 3)
        for offer in result.findall("./shop/offers/offer"):
            self.assertEqual(offer.findtext("name"), offer.findtext("name_ua"))
            self.assertEqual(offer.findtext("description"), offer.findtext("description_ua"))
        self.assertIsNone(source.find("./shop/offers/offer/name"))

    def test_missing_optional_characteristics(self):
        root = ET.fromstring(SOURCE)
        for offer in root.findall("./shop/offers/offer"):
            for param in offer.findall("param"):
                offer.remove(param)
        result = convert(root).getroot()
        self.assertEqual(len(result.findall("./shop/offers/offer")), 3)
        self.assertFalse(result.findall("./shop/offers/offer/param"))

    def test_bad_image_rejected(self):
        root = ET.fromstring(SOURCE)
        root.find("./shop/offers/offer/picture").text = "https://example.com/a+b.png"
        with self.assertRaisesRegex(ValueError, "picture URL"):
            convert(root)

    def test_wrong_availability_rejected(self):
        root = ET.fromstring(SOURCE)
        root.find("./shop/offers/offer").set("available", "false")
        with self.assertRaisesRegex(ValueError, "Availability mismatch"):
            convert(root)


if __name__ == "__main__":
    unittest.main()
