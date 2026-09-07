#!/usr/bin/env python
import os

from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), "README.md")) as f:
    long_description = f.read()

# Textual draws, `ptyhost` runs the program, and `pyte` holds the parser
# and the screen.
#
# **No prompt_toolkit, and not even in the closure.** The pure layer used
# to sit in `ptterm`, which is the prompt_toolkit widget, so this package
# pulled the toolkit in behind it and only a test kept it out of the
# code. It is in `pyte` now, where it belongs. Lillecarl/pymux#11.
requirements = [
    "textual",
    "ptyhost",
    "pyte",
]


setup(
    name="txterm",
    version="0.1",
    license="LICENSE",
    url="https://github.com/Lillecarl/txterm",
    description="A terminal widget for Textual.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages("."),
    install_requires=requirements,
    package_data={"txterm": ["py.typed"]},
    entry_points={
        "console_scripts": ["txterm = txterm.app:main"],
    },
    python_requires=">=3.10",
)
