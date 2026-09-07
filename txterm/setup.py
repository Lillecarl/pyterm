#!/usr/bin/env python
import os

from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), "README.md")) as f:
    long_description = f.read()

# Textual draws, `ptyhost` runs the program, and `ptterm` holds the
# parser and the screen.
#
# **The third one is a debt and not a design.** The pure layer belongs
# in `pyte`, and it sits in `ptterm` because that is where it was
# written. Nothing of prompt_toolkit comes with it: `tests/test_the_
# layers.py` names every module of ptterm this package touches, and
# that list is what the move has to carry. Lillecarl/pymux#11.
requirements = [
    "textual",
    "ptyhost",
    "ptterm",
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
