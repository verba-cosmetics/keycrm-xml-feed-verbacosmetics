import os
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = "https://openapi.keycrm.app/v1"
API_KEY = os.environ["KEYCRM_API_KEY"]
OUTPUT = Path("products.xml")

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})


def get_all(endpoint, params=None):
    """Завантажує всі сторінки API."""
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

        # Типова структура списку: {"data": [...]}.
        # За потреби адаптуй до фактичної відповіді KeyCRM.
        batch = result.get("data", [])
        if not isinstance(batch, list):
            raise ValueError(
                f"Невідома структура відповіді {endpoint}"
            )

        items.extend(batch)

        # Перевір пагінацію за реальною відповіддю API.
        meta = result.get("meta", {})
        last_page = meta.get("last_page")

        if last_page is not None:
            if page >= int(last_page):
                break
        elif len(batch) < 50:
            break

        page += 1

    return items


def get_quantity(stock):
    quantity = float(stock.get("quantity") or 0)
    reserve = float(stock.get("reserve") or 0)
    return max(0, quantity - reserve)


def main():
    offers = get_all("offers", {"include": "product"})
    stocks = get_all("offers/stocks")

    # ВАЖЛИВО: назву ключа ID треба підтвердити
    # за реальною відповіддю GET /offers/stocks.
    stock_by_offer = {}

    for stock in stocks:
        offer_id = stock.get("offer_id", stock.get("id"))
        if offer_id is not None:
            stock_by_offer[str(offer_id)] = get_quantity(stock)

    root = ET.Element("products")

    for offer in offers:
        product = offer.get("product") or {}
        offer_id = offer.get("id")

        if offer_id is None:
            continue

        available = stock_by_offer.get(str(offer_id), 0)

        item = ET.SubElement(root, "product")
        ET.SubElement(item, "id").text = str(offer_id)
        ET.SubElement(item, "name").text = str(
            product.get("name") or offer.get("name") or ""
        )
        ET.SubElement(item, "sku").text = str(
            offer.get("sku") or ""
        )
        ET.SubElement(item, "price").text = str(
            offer.get("price") or 0
        )
        ET.SubElement(item, "quantity").text = str(
            int(available)
        )

        barcode = offer.get("barcode")
        if barcode:
            ET.SubElement(item, "barcode").text = str(barcode)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"XML сформовано: {OUTPUT}")


if __name__ == "__main__":
    main()
