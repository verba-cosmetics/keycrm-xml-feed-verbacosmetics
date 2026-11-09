"""Generate EVA-compatible YML feed from KeyCRM catalog offers."""
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

import requests
from dynamic_attributes import custom_field_names, product_parameters

BASE_URL = "https://openapi.keycrm.app/v1"
OUTPUT = Path("pricelists/eva.xml")
CATEGORY_NAME = "Продукти"
VENDOR = "Verba Cosmetics"

# Stable EVA feed category IDs. Set eva_id only after confirming EVA catalog IDs.
FEED_CATEGORIES = {
    "cream": ("101", "Креми для рук"),
    "gloss": ("102", "Блиски для губ"),
}

# SKU selection and marketplace category IDs are the only product mappings kept
# in code. No product characteristic, volume or material is hard-coded here.
CATALOG = {
    "BHCCD": {"category": "cream", "name": "Крем для рук Verba Cosmetics Cashmere Dream бар'єрний", "description": "Бар'єрний крем для рук Verba Cosmetics Cashmere Dream для щоденного догляду за шкірою рук."},
    "LGC": {"category": "gloss", "name": "Блиск для губ Verba Cosmetics Coconut з пептидами та вітаміном C 15 мл", "description": "Блиск для губ Verba Cosmetics Coconut з пептидами та вітаміном C для декоративного макіяжу губ."},
    "LGLECCPC": {"category": "gloss", "name": "Блиск для губ Verba Cosmetics Crystal Caramel з пептидами та вітаміном C 15 мл", "description": "Блиск для губ Verba Cosmetics Crystal Caramel з пептидами та вітаміном C для декоративного макіяжу губ."},
}


def clean(value):
    # XML 1.0 forbids most control characters.
    return "".join(ch for ch in str(value or "") if ord(ch) >= 32 or ch in "\t\n\r")


def get_all(session, endpoint, params=None):
    items, page = [], 1
    while True:
        query = dict(params or {}, page=page, limit=50)
        response = session.get(f"{BASE_URL}/{endpoint}", params=query, timeout=30)
        response.raise_for_status()
        result = response.json()
        batch = result.get("data", [])
        if not isinstance(batch, list):
            raise ValueError(f"Unexpected KeyCRM response for {endpoint}")
        items.extend(batch)
        last_page = (result.get("meta") or {}).get("last_page")
        if (last_page is not None and page >= int(last_page)) or (last_page is None and len(batch) < 50):
            return items
        page += 1


def product_category_ids(product):
    found = set()
    for key in ("category_id", "categoryId"):
        if product.get(key) is not None:
            found.add(str(product[key]))
    category = product.get("category")
    if isinstance(category, dict):
        if category.get("id") is not None:
            found.add(str(category["id"]))
    elif category is not None:
        found.add(str(category))
    for entry in product.get("categories") or []:
        if isinstance(entry, dict) and entry.get("id") is not None:
            found.add(str(entry["id"]))
        elif isinstance(entry, (str, int)):
            found.add(str(entry))
    return found


def as_number(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid numeric value: {value!r}")


def available_stock(record):
    # Conservative: do not advertise reserved items as available.
    return max(0, int(as_number(record.get("quantity")) - as_number(record.get("in_reserve", record.get("reserve")))))


def stock_lookup(stocks):
    totals = defaultdict(int)
    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        offer_id = stock.get("offer_id")
        if offer_id is None and isinstance(stock.get("offer"), dict):
            offer_id = stock["offer"].get("id")
        if offer_id is not None:
            totals[str(offer_id)] += available_stock(stock)
    return dict(totals)


def image_urls(value):
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            yield value
    elif isinstance(value, list):
        for part in value:
            yield from image_urls(part)
    elif isinstance(value, dict):
        for key in ("url", "image_url", "src", "original_url", "path", "link"):
            if value.get(key):
                yield from image_urls(value[key])
                break


def pictures(product, offer):
    urls = []
    for source, keys in ((product, ("attachments_data", "images", "photos", "picture", "image", "thumbnail_url")),
                         (offer, ("thumbnail_url", "image_url", "image"))):
        for key in keys:
            for raw in image_urls(source.get(key)):
                url = quote(raw, safe=":/?&=%#@+;,$-_.!~*'()")
                parsed = urlsplit(url)
                if parsed.scheme == "https" and parsed.netloc and url not in urls:
                    urls.append(url)
    return urls[:15]


def render_feed(categories, products, offers, stocks, custom_fields=None):
    category_id = next((str(c["id"]) for c in categories if
                        str(c.get("name") or c.get("title") or "").strip().casefold() == CATEGORY_NAME.casefold()), None)
    if category_id is None:
        raise ValueError(f"KeyCRM category '{CATEGORY_NAME}' not found")

    by_id = {str(p["id"]): p for p in products if isinstance(p, dict) and p.get("id") is not None}
    by_stock = stock_lookup(stocks)
    field_names = custom_field_names(custom_fields or [])
    root = ET.Element("yml_catalog", {"date": datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M")})
    shop = ET.SubElement(root, "shop")
    ET.SubElement(shop, "name").text = VENDOR
    ET.SubElement(shop, "currencies").append(ET.Element("currency", {"id": "UAH", "rate": "1"}))
    groups = ET.SubElement(shop, "categories")
    for cat_id, name in FEED_CATEGORIES.values():
        ET.SubElement(groups, "category", {"id": cat_id}).text = name
    listing = ET.SubElement(shop, "offers")
    seen_ids, seen_skus = set(), set()
    for offer in offers:
        if not isinstance(offer, dict) or offer.get("is_archived"):
            continue
        sku = str(offer.get("sku") or "").strip()
        cfg = CATALOG.get(sku)
        if not cfg:
            continue
        parent = offer.get("product") if isinstance(offer.get("product"), dict) else {}
        prod_id = offer.get("product_id") or parent.get("id")
        product = by_id.get(str(prod_id), parent)
        if product.get("is_archived") or category_id not in product_category_ids(product):
            continue
        offer_id = offer.get("id")
        if offer_id is None or str(offer_id) in seen_ids or sku in seen_skus:
            raise ValueError(f"Missing/duplicate offer ID or SKU: {sku}")
        price = as_number(offer.get("price"))
        if price <= 0:
            raise ValueError(f"Invalid price for {sku}")
        urls = pictures(product, offer)
        if not urls:
            raise ValueError(f"No public HTTPS image URL for {sku}; do not publish incomplete feed")
        quantity = by_stock.get(str(offer_id), available_stock(offer))
        params = product_parameters(product, offer, field_names)
        if len(params) < 2:
            raise ValueError(
                f"Missing public KeyCRM characteristics for SKU {sku}: "
                f"found {len(params)}. Add product properties/custom fields "
                f"(including 'Об'єм' with units when appropriate) in KeyCRM."
            )
        cat_id = FEED_CATEGORIES[cfg["category"]][0]
        node = ET.SubElement(listing, "offer", {"id": str(offer_id), "available": str(quantity > 0).lower()})
        fields = {"price": format(price, "f"), "stock_quantity": str(quantity),
                  "currencyId": "UAH", "categoryId": cat_id}
        for tag, value in fields.items():
            ET.SubElement(node, tag).text = clean(value)
        for url in urls:
            ET.SubElement(node, "picture").text = url
        for tag, value in (("vendor", VENDOR), ("article", sku),
                           ("name_ua", cfg["name"]), ("description_ua", cfg["description"])):
            ET.SubElement(node, tag).text = clean(value)
        for name, value in params.items():
            ET.SubElement(node, "param", {"name": clean(name)}).text = clean(value)
        seen_ids.add(str(offer_id))
        seen_skus.add(sku)
    if seen_skus != set(CATALOG):
        raise ValueError(f"Catalog mismatch, missing SKUs: {sorted(set(CATALOG)-seen_skus)}")
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def main():
    api_key = os.environ["KEYCRM_API_KEY"]
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    tree = render_feed(
        get_all(session, "products/categories"),
        get_all(session, "products", {"include": "custom_fields"}),
        get_all(session, "offers", {"include": "product"}),
        get_all(session, "offers/stocks"),
        get_all(session, "custom-fields", {"include": "options"}),
    )
    tmp = OUTPUT.with_suffix(".xml.tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    tmp.replace(OUTPUT)
    print(f"EVA YML generated: {OUTPUT}; offers: {len(tree.getroot().findall('./shop/offers/offer'))}")


if __name__ == "__main__":
    main()
