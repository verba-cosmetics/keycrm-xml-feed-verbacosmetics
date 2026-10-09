
    root = ET.Element("products")

    for offer in offers:
        product = offer.get("product") or {}

        print("PRODUCT CATEGORY DEBUG:", product.get("category"))

        if product.get("category") != "Продукти":
            continue

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
        ET.SubElement(item, "quantity").text = str(int(available))

        barcode = offer.get("barcode")
        if barcode:
            ET.SubElement(item, "barcode").text = str(barcode)
