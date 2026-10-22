"""SDL nanopore automated analysis pipeline.

Three selectable event detectors (level / burst / plateau) share one
baseline/estimation -> detection -> feature -> export pipeline. Feature-table
columns follow the lab spec. Anomaly detection and plotting are optional mods.
"""

__version__ = "2.1.0"
