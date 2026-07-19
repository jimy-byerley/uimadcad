import os
import importlib.metadata

# current software version from pyproject.toml
version = importlib.metadata.version("uimadcad")
# determine the current software's ressource directory
resourcedir = os.path.abspath(__file__ + '/..')
