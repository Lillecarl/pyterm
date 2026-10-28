"""
The page around the galleries: one section per picture check.

The sections arrive as JSON in the environment; the runs arrive as
store paths beside them. This copies each run's tree into the site and
writes the index that inlines every picture it finds there, with the
run's log linked beside it. The page is the point, so the markup is
plain and carries no script.
"""

import html
import json
import os
import shutil
import sys
from pathlib import Path

STYLE = """
body { font-family: sans-serif; margin: 2rem auto; max-width: 60rem;
       line-height: 1.5; }
section { margin: 2rem 0; }
body.wide { max-width: none; margin: 2rem; }
.row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; }
.row figure { flex: 1 1 18rem; max-width: 32rem; }
figure { margin: 1rem 0; }
figure img { max-width: 100%; height: auto; display: block;
             border: 1px solid #444; }
figcaption { color: #888; font-size: 0.85rem; }
header p { color: #555; }
"""


#: The pictures of one directory that go first, in this order: the
#: terminal bare, the terminal through pymux, pymux drawing it itself,
#: and what differs. The rest follow by name.
FIRST = ("bare.png", "pymux.png", "pillow.png", "difference.png")


def _place(picture: Path):
    name = picture.name
    return (FIRST.index(name) if name in FIRST else len(FIRST), name)


def pictures_of(section_dir: Path):
    """
    Every picture in the run's tree, a row for each directory, in the
    order a person walks it: the pictures of one fixture side by side.
    """
    rows: dict[Path, list[Path]] = {}
    for picture in sorted(section_dir.rglob("*.png")):
        rows.setdefault(picture.parent, []).append(picture)
    return [sorted(row, key=_place) for row in rows.values()]


def section_html(section, site: Path) -> str:
    name = html.escape(section["name"])
    room = site / name
    shutil.copytree(section["run"], room, dirs_exist_ok=True, ignore=shutil.ignore_patterns("status"))
    figures = []
    for row in pictures_of(room):
        cells = []
        for picture in row:
            here = picture.relative_to(site)
            caption = picture.relative_to(room)
            cells.append(
                '<figure><img loading="lazy" src="%s">'
                "<figcaption>%s</figcaption></figure>" % (html.escape(str(here)), html.escape(str(caption)))
            )
        figures.append('<div class="row">%s</div>' % "".join(cells))
    log = room / "log"
    log_link = ' <a href="%s">the run\'s log</a>' % (name + "/log") if log.exists() else ""
    return '<section id="%s"><h2>%s</h2><p>%s%s</p>%s</section>' % (
        name,
        html.escape(section["title"]),
        html.escape(section["text"]),
        log_link,
        "\n".join(figures),
    )


def main():
    site = Path(sys.argv[1])
    sections = json.loads(os.environ["sections"])
    site.mkdir(parents=True, exist_ok=True)
    body = "\n".join(section_html(section, site) for section in sections)
    title = "pymux, photographed"
    (site / "index.html").write_text(
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<title>%s</title><style>%s</style></head><body class="wide">'
        "<header><h1>%s</h1><p>Every picture the picture checks draw,"
        " inline and beside their logs. Nothing here is judged unless its"
        " section says so; the sections are the checks' runs, as they were"
        " built.</p></header>\n%s\n</body></html>\n" % (title, STYLE, title, body)
    )


main()
