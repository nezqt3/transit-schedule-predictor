import os
import sys


sys.path.insert(
    0,
    os.path.abspath(".."),
)


project = "Transport Delay Predictor"
author = "Hackathon Team"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]

exclude_patterns = []

html_theme = "sphinx_rtd_theme"

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}