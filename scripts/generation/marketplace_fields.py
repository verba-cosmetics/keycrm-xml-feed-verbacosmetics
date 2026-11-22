"""Explicit public KeyCRM product fields and marketplace formatting."""
from html import escape
from html.parser import HTMLParser
from xml.dom import minidom
import xml.etree.ElementTree as ET

def fields(entity):
    raw = entity.get("custom_fields") or []
    if isinstance(raw, dict):
        return raw
    return {str(x.get("uuid")): x.get("value") for x in raw if isinstance(x, dict) and x.get("uuid")}

def values(value):
    if isinstance(value, list):
        return [s for x in value for s in values(x)]
    if isinstance(value, dict):
        return values(value.get("name") or value.get("label") or value.get("value"))
    if value is None or isinstance(value, bool):
        return []
    return [str(value).strip()] if str(value).strip() else []

def marketplace_fields(product, definitions):
    raw = fields(product)
    params = {}
    flag = raw.get("CT_1014")
    if isinstance(flag, list) and len(flag) == 1:
        flag = flag[0]
    # Fail closed if the toggle is missing or unrecognized.
    enabled = str(flag).strip().casefold() in ("true", "1")
    kind = values(raw.get("CT_1015"))
    if kind:
        params["Вид"] = ", ".join(kind)
    volume = values(raw.get("CT_1016"))
    if volume:
        if len(volume) != 1 or not volume[0].isdigit() or int(volume[0]) <= 0:
            raise ValueError("CT_1016 must be a positive integer in ml")
        # EVA attribute ID 100050 uses the numeric value (e.g. 30).
        params["Об'єм"] = volume[0]
    for item in definitions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("title") or "").strip()
        if name.casefold() == "активний компонент":
            components = values(raw.get(str(item.get("uuid"))))
            if components:
                params["Активний компонент"] = ", ".join(components)
    purpose = values(raw.get("CT_1018"))
    if purpose:
        params["Призначення"] = ", ".join(purpose)
    return enabled, params

def format_description(text):
    output = []
    in_list = False
    headings = {"переваги продукту", "як діє?", "ароматична композиція", "б'юті-поради", "б’юті-поради", "склад товару", "як використовувати", "точний склад вказано на упаковці."}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("• ", "- ")):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append("<li>" + escape(line[2:]) + "</li>")
            continue
        if in_list:
            output.append("</ul>")
            in_list = False
        if not line:
            continue
        heading = line.strip("*").strip()
        if heading.casefold() in headings or (line.startswith("**") and line.endswith("**")):
            output.append("<p><strong>" + escape(heading) + "</strong></p>")
        else:
            output.append("<p>" + escape(line) + "</p>")
    if in_list:
        output.append("</ul>")
    return "".join(output)

def write_eva_xml(tree, path):
    doc = minidom.parseString(ET.tostring(tree.getroot(), encoding="utf-8"))
    for node in doc.getElementsByTagName("description_ua"):
        plain = "".join(child.data for child in node.childNodes if child.nodeType in (child.TEXT_NODE, child.CDATA_SECTION_NODE))
        while node.firstChild:
            node.removeChild(node.firstChild)
        node.appendChild(doc.createCDATASection(format_description(plain)))
    path.write_bytes(doc.toxml(encoding="utf-8"))

class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("• ")
        elif tag == "br":
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("p", "li"):
            self.parts.append("\n")
    def handle_data(self, data):
        self.parts.append(data)

def plain_description(text):
    if not text.startswith(("<p>", "<ul>")):
        return text.strip()
    parser = PlainHTML()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts).strip()
