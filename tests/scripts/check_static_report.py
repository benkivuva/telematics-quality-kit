"""Check a generated report for external resources and active content."""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class ReportResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attributes: list[dict[str, str | None]] = []
        self._in_style = False
        self.styles: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.append(dict(attrs))
        if tag == "style":
            self._in_style = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)


def main() -> None:
    parser = ReportResourceParser()
    parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))
    parser.close()
    assert not ({"script", "link"} & set(parser.tags)), "report contains active/external tags"
    assert all(not ({"src", "href"} & attrs.keys()) for attrs in parser.attributes), (
        "report contains external references"
    )
    css = " ".join(parser.styles)
    assert not re.search(r"@import|url\s*\(", css, re.IGNORECASE), (
        "report CSS contains an external reference"
    )


if __name__ == "__main__":
    main()
