import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))

import unittest
import xml.etree.ElementTree as ET

from generate_rozetka import convert, write_rozetka_xml


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

    def test_html_description_cdata_and_eva_source_untouched(self):
        source = ET.fromstring(SOURCE)
        cream = source.find("./shop/offers/offer[@id='4']")
        html = "<p><strong>Переваги продукту</strong></p><ul><li>Зволоження &amp; догляд</li></ul>"
        cream.find("description_ua").text = html

        converted = convert(source)
        result = converted.getroot()
        self.assertEqual(result.find("./shop/offers/offer[@id='4']/description_ua").text, html)
        self.assertEqual(result.find("./shop/offers/offer[@id='4']/description").text, html)
        self.assertEqual(cream.findtext("description_ua"), html)
        self.assertIsNone(cream.find("description"))

        with TemporaryDirectory() as directory:
            path = Path(directory) / "rozetka.xml"
            write_rozetka_xml(converted, path)
            output = path.read_text(encoding="utf-8")
            self.assertIn(f"<description_ua><![CDATA[{html}]]></description_ua>", output)
            self.assertIn(f"<description><![CDATA[{html}]]></description>", output)
            self.assertEqual(
                ET.parse(path).findtext("./shop/offers/offer[@id='4']/description_ua"),
                html,
            )

    def test_plain_description_falls_back_to_html_paragraphs(self):
        source = ET.fromstring(SOURCE)
        converted = convert(source).getroot()
        self.assertEqual(
            converted.findtext("./shop/offers/offer[@id='4']/description_ua"),
            "<p>Бар&#x27;єрний крем для щоденного догляду за шкірою рук.</p>",
        )

    def test_products_without_params_are_kept(self):
        root = ET.fromstring(SOURCE)
        for offer in root.findall("./shop/offers/offer"):
            for param in offer.findall("param"):
                offer.remove(param)
        converted = convert(root).getroot()
        self.assertEqual(len(converted.findall("./shop/offers/offer")), 3)

    def test_rozetka_volume_keeps_unit(self):
        source = ET.fromstring(SOURCE)
        cream = source.find("./shop/offers/offer[@id='4']")
        ET.SubElement(cream, "param", {"name": "Об'єм"}).text = "30"
        converted = convert(source).getroot()
        self.assertEqual(converted.find("./shop/offers/offer[@id='4']/param[@name=\"Об'єм\"]").text, "30 мл")

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
