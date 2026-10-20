#!/usr/bin/env python3
"""Convert an HTML document on stdin to plain text on stdout.

Reads stdin, writes stdout. Example:

    python3 h2t.py < page.body > page.txt

script/style/noscript/svg content is dropped. Block elements become line
breaks, list items get a "- " prefix, and table cells are separated by a
tab so tabular pricing pages survive the conversion.

JavaScript-rendered pages convert to little or nothing, because the text
is not in the served HTML. That is a property of the source page, not a
bug here; such a page must be read with a browser or a different
endpoint (for example its llms.txt or a .md twin).
"""
import sys
from html.parser import HTMLParser

DROP = {"script", "style", "noscript", "svg", "head"}
BLOCK = {
    "p", "div", "section", "article", "header", "footer", "main", "aside",
    "nav", "ul", "ol", "table", "thead", "tbody", "tr", "form", "figure",
    "blockquote", "pre", "hr", "br",
}
HEAD = {"h1", "h2", "h3", "h4", "h5", "h6"}


class T(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0
        self.li = False

    def handle_starttag(self, tag, attrs):
        if tag in DROP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in BLOCK or tag in HEAD:
            self.out.append("\n")
        if tag == "li":
            self.out.append("\n- ")
        if tag == "td" or tag == "th":
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in DROP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in BLOCK or tag in HEAD or tag == "li":
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if data.strip():
            self.out.append(data)

    def text(self):
        raw = "".join(self.out)
        lines = [" ".join(ln.split()) for ln in raw.splitlines()]
        keep = [ln for ln in lines if ln]
        return "\n".join(keep) + "\n"


def main():
    p = T()
    p.feed(sys.stdin.read())
    sys.stdout.write(p.text())


if __name__ == "__main__":
    main()
