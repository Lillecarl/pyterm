"""
Lay out one source's Sphinx project in the unpacked source, and build it.

The spec arrives as JSON in `$docs`: the name, the modules the API
reference walks, and the links the index ends with. The index is the
README, then a page for each file in `docs/`, then the API reference.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

confdir, out = sys.argv[1], sys.argv[2]
spec = json.loads(os.environ["docs"])
root = Path.cwd()


def toctree(caption: str, entries: list[str]) -> str:
    if not entries:
        return ""
    lines = "".join(f"   {entry}\n" for entry in entries)
    return f"\n.. toctree::\n   :maxdepth: 1\n   :caption: {caption}\n\n{lines}"


# A toctree entry takes an absolute URL only, which is why a link names one.
def links(entries: list[dict]) -> str:
    return toctree("See also", [f"{link['title']} <{link['url']}>" for link in entries])


pages = sorted(
    str(page.with_suffix("").relative_to(root)) for page in (root / "docs").glob("*") if page.suffix in {".md", ".rst"}
)
if spec["modules"]:
    api = "".join(f"   {module}\n" for module in spec["modules"])
    (root / "api.rst").write_text(
        "API reference\n=============\n\n.. autosummary::\n   :toctree: _autosummary\n   :recursive:\n\n" + api
    )
    pages.append("api")
(root / "index.rst").write_text(
    ".. include:: README.md\n   :parser: myst_parser.sphinx_\n" + toctree("Contents", pages) + links(spec["links"])
)

subprocess.run(
    [
        sys.executable, "-m", "sphinx",
        "--builder", "html",
        "--conf-dir", confdir,
        "--doctree-dir", os.path.join(os.environ["TMPDIR"], "doctrees"),
        "--jobs", "auto",
        "--quiet",
        str(root), out,
    ],
    check=True,
)
