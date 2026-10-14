"""The one Sphinx configuration every source's site builds with. `build.py` lays the project out."""

import json
import os

project = json.loads(os.environ["docs"])["name"]
master_doc = "index"
include_patterns = ["index.rst", "api.rst", "_autosummary/**", "docs/**"]

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
myst_heading_anchors = 3

autosummary_generate = True
autodoc_default_options = {"members": True}

html_theme = "furo"
html_title = project
html_copy_source = False
