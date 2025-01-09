# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from dataclasses import asdict
from sphinxawesome_theme import ThemeOptions


# -- Project information -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Kompass'
release = '2.0'
author = 'The Kompass Team'
copyright = f'2025, {author}'

# -- General configuration -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

templates_path = ['_templates']
exclude_patterns = []

language = 'de'

# -- Options for HTML output ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinxawesome_theme'
html_static_path = ['_static']


# -- Sphinxawsome-theme options ------------------------------------------------
# https://sphinxawesome.xyz/how-to/configure/

html_logo = "_static/favicon2.png"
html_favicon  = "_static/favicon2.png"

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
