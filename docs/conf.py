# docs/conf.py

import os
import sys
from datetime import datetime

# -- Path setup --------------------------------------------------------------

sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -----------------------------------------------------

project = "RSVP Bot"
author = "Giacomo Terreran"
copyright = f"{datetime.now().year}, {author}"

# -- General configuration ---------------------------------------------------

html_static_path = ["_static"]
html_logo = "_static/rsvp_bot.png"


extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

autosummary_generate = False
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
    "special-members": "__init__",
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autodoc_member_order = "bysource"

autodoc_mock_imports = [
    "discord",
    "discord.ext",
    "discord.app_commands",
]
autoclass_content = "class"

autosectionlabel_prefix_document = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "discord": ("https://discordpy.readthedocs.io/en/stable/", None),
}

# -- Napoleon settings -------------------------------------------------------

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_ivar = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = False

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
