"""Read public product characteristics from KeyCRM, never from static SKU data.

Supported sources:
* Product / offer properties and attributes (name-value pairs).
* Product / offer custom_fields, resolved against GET /custom-fields UUID metadata.

SKU and marketplace category mappings are integration configuration, not product specs.
Do not guess product volume from shipping weight or package dimensions.
"""
import re
from collections import OrderedDict

# Never expose internal business data as marketplace product characteristics.
PRIVATE = re.compile(
    r"закуп|собіварт|прибут|марж|постачаль|внутріш|коментар менедж|"
    r"purchase|cost|profit|margin|supplier|internal|secret|token|password|api.key|"
    r"iban|рахунок|email|телефон|phone|ідентифікатор|uuid",
    re.IGNORECASE,
)


def text_value(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(v for item in value if (v := text_value(item)))
    if isinstance(value, dict):
        for field in ("value", "name", "title", "label"):
            if field in value:
                return text_value(value[field])
        return ""
    return str(value).strip()


def custom_field_names(definitions):
    """Map KeyCRM field UUIDs to their UI titles."""
    names = {}
    for item in definitions:
        if not isinstance(item, dict):
            continue
        uuid = item.get("uuid")
        title = item.get("name") or item.get("title") or item.get("label")
        if uuid and title:
            names[str(uuid)] = str(title).strip()
    return names


def pairs(raw, definitions=None):
    """Yield (display name, value) from either list or mapping representations."""
    if isinstance(raw, dict):
        for key, value in raw.items():
            yield str((definitions or {}).get(str(key), key)), value
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            uuid = str(item.get("uuid") or item.get("field_uuid") or "")
            label = item.get("name") or item.get("title") or item.get("label")
            if not label and uuid:
                label = (definitions or {}).get(uuid)
            if label and "value" in item:
                yield str(label), item["value"]


def product_parameters(product, offer, definitions=None):
    """All populated non-private characteristics; variant overrides base product."""
    result = OrderedDict()
    for entity in (product, offer):
        if not isinstance(entity, dict):
            continue
        for field in ("properties", "attributes"):
            for name, value in pairs(entity.get(field)):
                key = name.strip()
                val = text_value(value)
                if key and val and not PRIVATE.search(key):
                    result[key] = val
        # Resolve custom field UUID through /custom-fields metadata.
        for name, value in pairs(entity.get("custom_fields"), definitions):
            key = name.strip()
            val = text_value(value)
            if key and val and not PRIVATE.search(key):
                result[key] = val
    return result
