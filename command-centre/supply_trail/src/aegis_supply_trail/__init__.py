"""aegis_supply_trail — counterfeit note provenance inference."""
__version__ = "0.1.0"

from .engine import compute_provenance, compute_trail, compute_trails_all_modes

__all__ = ["compute_trail", "compute_trails_all_modes", "compute_provenance"]
