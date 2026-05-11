# El nombre de distribución es "ztc-tui" (el nombre "ztc" ya estaba tomado en
# PyPI por otro proyecto). El paquete importable, el comando CLI y el repo son
# "ztc"; solo la metadata del paquete usa el nombre con sufijo.
from importlib.metadata import version

__version__ = version("ztc-tui")
