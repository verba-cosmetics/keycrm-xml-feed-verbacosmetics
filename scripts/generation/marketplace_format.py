"""Service fields and safe presentation formatting for EVA."""
from html import escape
from html.parser import HTMLParser
from xml.dom import minidom
import xml.etree.ElementTree as ET


def extract_availability(params):
    """Consume the private control; false overrides physical stock."""
    values = []
    for key in list(params):
        if key.strip().casefold() == "наявність":
            values.append(params.pop(key).strip().casefold())
    if not values:
        return None
    if any(value not in ("true", "false") for value in values):
        raise ValueError("Наявність must be true or false")
    return all(value == "true" for value in values)


HEADINGS = {
    "переваги продукту", "переваги", "б'юті-поради", "б’юті-поради",
    "ароматична композиція", "спосіб застосування", "активні компоненти",
}


def format_description(text):
    """Render plain CRM content as escaped, minimal HTML."""
    output = []
    in_list = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                output.append("</ul>")
                in_list = False
            continue
        if line.startswith(("• ", "- ")):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append("<li>" + escape(line[2:]) + "</li>")
            continue
        if in_list:
            output.append("</ul>")
            in_list = False
        if line.casefold() in HEADINGS:
            output.append("<h3>" + escape(line) + "</h3>")
        else:
            output.append("<p>" + escape(line) + "</p>")
    if in_list:
        output.append("</ul>")
    return "".join(output)


def write_eva_xml(tree, path):
    """Use actual CDATA for EVA HTML descriptions, not escaped markup."""
    doc = minidom.parseString(ET.tostring(tree.getroot(), encoding="utf-8"))
    for node in doc.getElementsByTagName("description_ua"):
        plain = "".join(child.data for child in node.childNodes
                        if child.nodeType in (child.TEXT_NODE, child.CDATA_SECTION_NODE))
        while node.firstChild:
            node.removeChild(node.firstChild)
        node.appendChild(doc.createCDATASection(format_description(plain)))
    path.write_bytes(doc.toxml(encoding="utf-8"))


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("• ")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "h3", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_description(text):
    """Keep Rozetka description in its existing plain-text format."""
    if not text.startswith(("<p>", "<h3>", "<ul>")):
        return text.strip()
    parser = _PlainHTML()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts).strip()
