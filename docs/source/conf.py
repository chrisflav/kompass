# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
from dataclasses import asdict
from pathlib import Path

from sphinxawesome_theme import ThemeOptions

# `kompass.rules` — the API a section's finance rules are written against — is
# documented from its own docstrings, which were written for a rule author. It
# lives in the Django project directory, so that directory has to be importable
# here as it is at runtime.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jdav_web"))

# -- Project information -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Kompass"
release = "2.0"
author = "The Kompass Team"
copyright = f"2025, {author}"

# -- General configuration -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc"]

templates_path = ["_templates"]
exclude_patterns = []

language = "de"

# -- Options for autodoc -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html

# Declaration order, not alphabetical: the rules API is documented to be read
# top to bottom, and `Ruleset.inputs` before `Ruleset.transfers` is the order a
# ruleset is written in.
autodoc_member_order = "bysource"

# Nothing is mocked, and `kompass.rules` is why that is possible: the module
# imports the standard library and nothing else, no Django and no models, so
# autodoc importing it is as cheap and as side-effect-free as a ruleset
# importing it. Anything added here would be a sign that the rules API had
# grown a dependency a section's rules cannot have either.
autodoc_mock_imports = []

# -- Options for HTML output ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinxawesome_theme"
html_static_path = ["_static"]


# -- Sphinxawsome-theme options ------------------------------------------------
# https://sphinxawesome.xyz/how-to/configure/

html_logo = "_static/favicon.svg"
html_favicon = "_static/favicon.svg"

html_sidebars = {
    "about": ["sidebar_main_nav_links.html"],
    # "changelog": ["sidebar_main_nav_links.html"],
}

# Code blocks color scheme
pygments_style = "emacs"
pygments_style_dark = "emacs"

# Could be directly in html_theme_options, but this way it has type hints
#   from sphinxawesome_theme
theme_options = ThemeOptions(
    show_prev_next=True,
    show_breadcrumbs=True,
    main_nav_links={
        "Docs": "index",
        "About": "about",
        # "Changelog": "changelog"
    },
    show_scrolltop=True,
)

html_theme_options = asdict(theme_options)
