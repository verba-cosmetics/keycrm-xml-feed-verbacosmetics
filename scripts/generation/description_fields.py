"""Parse structured KeyCRM product Description into public XML fields.

Template (one field per line):
Опис: Customer-facing product description.
Тип засобу: Крем для рук
Об'єм: 30 мл

Descriptions without the template remain ordinary editorial descriptions.
Never infer net contents from the shipping weight/dimensions.
"""
import re
from collections import OrderedDict

from dynamic_attributes import PRIVATE

DESCRIPTION_KEYS = {"опис", "description", "опис товару"}
SPLIT = re.compile(r"^\s*([^:\n]{2,80}):\s*(.*?)\s*$")


def parse_description(raw):
    """Return (editorial_description, public_parameters) from KeyCRM description."""
    raw = str(raw or "").replace("\r\n", "\n").strip()
    if not raw:
        return "", OrderedDict()
    lines = raw.split("\n")
    # Treat as structured ONLY when the first line is an explicit description label.
    first = SPLIT.match(lines[0])
    if not first or first.group(1).strip().casefold() not in DESCRIPTION_KEYS:
        return raw, OrderedDict()
    text_parts = []
    params = OrderedDict()
    current = "description"
    for line in lines:
        match = SPLIT.match(line)
        if match:
            key, val = match.group(1).strip(), match.group(2).strip()
            if key.casefold() in DESCRIPTION_KEYS:
                current = "description"
                if val:
                    text_parts.append(val)
                continue
            # Never silently publish internal fields from the description.
            current = "private" if PRIVATE.search(key) else key
            if current != "private" and val:
                params[key] = val
            continue
        if current == "description" and line.strip():
            text_parts.append(line.strip())
        elif current != "private" and line.strip():
            params[current] = (params.get(current, "") + " " + line.strip()).strip()
    return "\n".join(text_parts), params
