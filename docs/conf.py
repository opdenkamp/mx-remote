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
html_static_path = []
