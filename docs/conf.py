######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Sphinx configuration for the mx_remote documentation site.

The guides in this directory are the prose; the API reference is generated from
the package's own docstrings, so `mx_remote` must be importable when this runs.
The workflow installs it rather than mocking it: a reference built against
mocks documents the mocks on the day an import breaks.
'''

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent

project = 'mx_remote'
author = 'Lars Op den Kamp'
copyright = '2021-2026 Op den Kamp IT Solutions'

# Read from the package the same way pyproject.toml does, so the site cannot
# report a version the package does not carry.
release = re.search(r"VERSION = '([^']+)'",
                    (_ROOT / 'mx_remote' / 'const.py').read_text(encoding='utf-8')).group(1)
version = release

extensions = [
    'myst_parser',              # the guides are markdown, and stay readable on GitHub
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
]

# Anchors for the '#section' links the guides use between each other.
myst_heading_anchors = 3

exclude_patterns = ['_build', 'requirements.txt']

autodoc_default_options = {
    'members': True,
    'show-inheritance': True,
    'member-order': 'bysource',
}
# A member with no docstring says nothing a reader cannot get from the
# signature, and there are enough of them to bury the ones that do.
autodoc_typehints = 'description'
autodoc_class_signature = 'separated'

intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

html_theme = 'furo'
html_title = f'mx_remote {release}'
html_static_path = ['_static']
html_css_files = ['brand.css']
# The ring alone, because the full mark is portrait and would letterbox down
# to a few unreadable pixels in a tab.
html_favicon = '_static/favicon.svg'

# The palette is the one opdenkamp-it.nl uses, so the site and the docs read as
# one place: slate text, teal accents, and a near-black teal ground when dark.
# Furo derives the rest of its colours from these, and applies the light set to
# both themes, so the dark set only names what differs.
html_theme_options = {
    'light_logo': 'logo.svg',
    'dark_logo': 'logo-dark.svg',
    'light_css_variables': {
        'font-stack': '"Inter Variable", Inter, system-ui, -apple-system, sans-serif',
        'font-stack--monospace': '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, monospace',
        'color-brand-primary': '#0f4c5c',
        'color-brand-content': '#117a8b',
        'color-brand-visited': '#0f4c5c',
        'color-foreground-primary': '#0f172a',
        'color-foreground-secondary': '#475569',
        'color-foreground-muted': '#64748b',
        'color-foreground-border': '#e2e8f0',
        'color-background-primary': '#ffffff',
        'color-background-secondary': '#f8fafc',
        'color-background-border': '#e2e8f0',
        'color-inline-code-background': '#f1f5f9',
        'color-api-name': '#0f4c5c',
        'color-api-pre-name': '#117a8b',
    },
    'dark_css_variables': {
        'color-brand-primary': '#5aafc0',
        'color-brand-content': '#5aafc0',
        'color-brand-visited': '#8fc9d5',
        'color-foreground-primary': '#e2e8f0',
        'color-foreground-secondary': '#94a3b8',
        'color-foreground-muted': '#7d8ea0',
        'color-foreground-border': '#1c414d',
        'color-background-primary': '#0a1f26',
        'color-background-secondary': '#0d2b34',
        'color-background-border': '#1c414d',
        'color-inline-code-background': '#12333d',
        'color-api-name': '#5aafc0',
        'color-api-pre-name': '#8fc9d5',
    },
}
