"""Experimental shape discovery: PELT, DTW/Fréchet, DBA, vocabulary.

Nothing in this package is enabled by default. Every describer registered here
has ``maturity = "experimental"`` and every description carries an
``experimental`` flag. The legacy vocabulary did not pass the project's own
AUC ≥ 0.85 gate; the numbers are retained in :data:`model.GATE_NOTE`.

Importing this package is safe without the ``research`` extra: ``ruptures`` and
``scikit-learn`` are imported only when a fit/decode actually runs.
"""
from __future__ import annotations

from .corpus import EventCorpus
from .curves import (DISTANCES, TIME_FLOOR_MS, dba, discrete_frechet,
                     distance_matrix, dist, dtw, make_known_shape, medoid,
                     represent)
from .deps import (INSTALL_HINT, REQUIRED, ResearchDependencyError,
                   missing_dependencies, require_research)
from .fragments import (Fragment, FragmentParams, cluster_fragments,
                        detect_breakpoints, extract_fragment_spans,
                        extract_fragments)
from .model import (GATE_NOTE, PELTDescriber, ShapeModel,
                    ShapeVocabularyMethod, clear_active_model,
                    get_active_model, set_active_model)
from .nulls import (auc, event_metrics, leave_one_file, match_depth_dwell,
                    null_report, phase_randomize, recurrence_score,
                    shuffle_samples, synth_flat, synth_random,
                    synth_telegraph)
from .workflows import (build_corpus, decode_corpus, decode_files,
                        fit_vocabulary, write_decoded_by_source)

__all__ = [
    "EventCorpus", "Fragment", "FragmentParams", "ShapeModel",
    "ShapeVocabularyMethod", "PELTDescriber", "GATE_NOTE",
    "set_active_model", "get_active_model", "clear_active_model",
    "missing_dependencies", "require_research", "ResearchDependencyError",
    "REQUIRED", "INSTALL_HINT",
    "represent", "dtw", "discrete_frechet", "dba", "distance_matrix",
    "dist", "DISTANCES", "medoid", "make_known_shape", "TIME_FLOOR_MS",
    "detect_breakpoints", "extract_fragment_spans", "extract_fragments",
    "cluster_fragments",
    "build_corpus", "fit_vocabulary", "decode_corpus", "decode_files",
    "write_decoded_by_source",
    "auc", "null_report", "leave_one_file", "event_metrics",
    "recurrence_score", "phase_randomize", "shuffle_samples",
    "synth_flat", "synth_telegraph", "synth_random", "match_depth_dwell",
]
