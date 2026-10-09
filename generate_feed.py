
import os
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = "https://openapi.keycrm.app/v1"
API_KEY = os.environ["KEYCRM_API_KEY"]
OUTPUT = Path("products.xml")
CATEGORY_NAME = "Продукти"

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})


def get_all(endpoint, params=None):
    items = []
    page = 1

    while True:
        query = dict(params or {})
        query.update({"page": page, "limit": 50})

        response = session.get(
            f"{BASE_URL}/{endpoint}",
            params=query,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        batch = result.get("data", [])
        if not isinstance(batch, list):
            raise ValueError(
                f"Unexpected response from {endpoint}: "
                f"{str(result)[:500]}"
            )

        items.extend(batch)

        meta = result.get("meta", {})
        last_page = meta.get("last_page")

        if last_page is not None:
            if page >= int(last_page):
                break
        elif len(batch) < 50:
            break

        page += 1

    return items


def get_id(obj):
    if not isinstance(obj, dict):
        return None

    for key in ("id", "category_id", "product_id", "offer_id"):
        if obj.get(key) is not None:
            return str(obj[key])

    return None


def find_category_id(categories, wanted_name):
    for category in categories:
        if not isinstance(category, dict):
            continue

        name = category.get("name") or category.get("title")
        if isinstance(name, str) and name.strip().casefold() == wanted_name.casefold():
            category_id = category.get("id")
            if category_id is not None:
                return str(category_id)

    return None


def product_category_ids(product):
    """Extract category IDs from common product response structures."""
    found = set()

    if not isinstance(product, dict):
        return found

    for key in ("category_id", "categoryId"):
        if product.get(key) is not None:
            found.add(str(product[key]))

    category = product.get("category")
    if isinstance(category, dict):
        category_id = category.get("id")
        if category_id is not None:
            found.add(str(category_id))
    elif isinstance(category, (int, str)):
        found.add(str(category))

    categories = product.get("categories")
    if isinstance(categories, list):
        for item in categories:
            if isinstance(item, dict) and item.get("id") is not None:
                found.add(str(item["id"]))
            elif isinstance(item, (int, str)):
                found.add(str(item))

    return found


def get_quantity(stock):
    quantity = float(stock.get("quantity") or 0)
    reserve = float(stock.get("reserve") or 0)
    return max(0, quantity - reserve)


def main():
    categories = get_all("products/categories")
    products = get_all("products")
    offers = get_all("offers", {"include": "product"})
    stocks = get_all("offers/stocks")

    category_id = find_category_id(categories, CATEGORY_NAME)

    if category_id is None:
        raise ValueError(
            f"Category '{CATEGORY_NAME}' not found. "
            f"Categories returned: {categories[:10]}"
        )

    print(f"Target category: {CATEGORY_NAME}, ID={category_id}")
    print(f"Products: {len(products)}, offers: {len(offers)}")

    products_by_id = {
        str(product["id"]): product
        for product in products
        if isinstance(product, dict) and product.get("id") is not None
    }

    stock_by_offer = {}
    for stock in stocks:
        if not isinstance(stock, dict):
            continue

        offer_id = stock.get("offer_id")
        if offer_id is None and isinstance(stock.get("offer"), dict):
            offer_id = stock["offer"].get("id")

        if offer_id is not None:
            stock_by_offer[str(offer_id)] = get_quantity(stock)

    root = ET.Element("products")
    included = 0
    category_matches = 0

    for offer in offers:
        embedded_product = offer.get("product") or {}
        product_id = embedded_product.get("id") or offer.get("product_id")

        product = products_by_id.get(
            str(product_id), embedded_product
        ) if product_id is not None else embedded_product

        category_ids = product_category_ids(product)

        if category_id not in category_ids:
            continue

        category_matches += 1

        name = product.get("name") or offer.get("name") or ""
        if name.strip().casefold() == "доставка":
            continue

        offer_id = offer.get("id")
        if offer_id is None:
            continue

        item = ET.SubElement(root, "product")
        ET.SubElement(item, "id").text = str(offer_id)
        ET.SubElement(item, "name").text = str(name)
        ET.SubElement(item, "sku").text = str(offer.get("sku") or "")
        ET.SubElement(item, "price").text = str(offer.get("price") or 0)
        ET.SubElement(item, "quantity").text = str(
            int(stock_by_offer.get(str(offer_id), 0))
        )

        barcode = offer.get("barcode")
        if barcode:
            ET.SubElement(item, "barcode").text = str(barcode)

        included += 1

    if category_matches == 0:
        raise ValueError(
            "No offers matched the target category ID. "
            "The product category field structure needs verification. "
            f"Example product: {products[0] if products else 'No products'}"
        )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)

    print(f"XML generated: {OUTPUT}")
    print(f"Products in category: {category_matches}")
    print(f"Products included in feed: {included}")


if __name__ == "__main__":
    main()
