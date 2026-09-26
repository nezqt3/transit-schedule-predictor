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
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

autosummary_generate = True
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = ["_templates"]

exclude_patterns = []

# sphinx_autodoc_typehints не может разрешить отложенные аннотации
# sqlalchemy/pydantic (SQLCoreOperations, JsonValue) — на вывод не влияет.
suppress_warnings = ["sphinx_autodoc_typehints.forward_reference"]

html_theme = "sphinx_rtd_theme"

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
