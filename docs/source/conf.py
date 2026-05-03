# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
from dataclasses import asdict
from pathlib import Path

import tomli
from sphinxawesome_theme import ThemeOptions

# -- Project information -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Kompass"
release = "2.0"
author = "The Kompass Team"
copyright = f"2025, {author}"

# -- General configuration -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

templates_path = ["_templates"]
exclude_patterns = []

language = "de"

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


# -- Kompass placeholder replacement ------------------------------------------
# Read configuration from settings.toml and replace hardcoded placeholders in
# all RST source files at build time.

_PLACEHOLDER_BASE_URL = "BASE_URL"
_PLACEHOLDER_CONTACT_MAIL = "digitales@placeholder-domain.de"


def _load_settings() -> dict:
    config_dir = os.environ.get("KOMPASS_CONFIG_DIR_PATH", "")
    settings_file = os.environ.get("KOMPASS_SETTINGS_FILE", "settings.toml")
    settings_path = Path(config_dir) / settings_file if config_dir else None

    if settings_path is None or not settings_path.exists():
        # Fall back to the deploy example config relative to this file
        settings_path = Path(__file__).parent.parent.parent / "deploy" / "config" / "settings.toml"

    if not settings_path.exists():
        return {}

    with open(settings_path, "rb") as f:
        return tomli.load(f)


_settings = _load_settings()


def _get_base_url() -> str | None:
    django = _settings.get("django", {})
    host = django.get("host") or django.get("base_url") or None
    if host is None:
        return None
    protocol = django.get("protocol") or "https"
    return f"{protocol}://{host}"


def _get_contact_mail() -> str | None:
    section = _settings.get("section", {})
    return section.get("digital_mail") or section.get("responsible_mail") or None


_base_url = _get_base_url()
_contact_mail = _get_contact_mail()


def _replace_placeholders(app, docname, source):
    if _contact_mail:
        source[0] = source[0].replace(_PLACEHOLDER_CONTACT_MAIL, _contact_mail)
    if _base_url:
        source[0] = source[0].replace(_PLACEHOLDER_BASE_URL, _base_url)


def setup(app):
    app.connect("source-read", _replace_placeholders)
