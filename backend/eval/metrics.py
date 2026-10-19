"""Timing error metrics: aligned syllables vs reference syllables (same lyrics, same order)."""

from typing import Dict, List

import numpy as np

GROSS_ERROR_SEC = 0.5


def timing_errors(results: List[dict], reference_starts: List[float]) -> np.ndarray:
    """Signed start errors in seconds (aligned − reference), syllable by syllable."""
    if len(results) != len(reference_starts):
        raise ValueError(f"{len(results)} aligned syllables vs {len(reference_starts)} in the reference")
    return np.array([r["start"] for r in results]) - np.array(reference_starts)


def summarize(errors: np.ndarray) -> Dict[str, float]:
    """Median absolute error, share within 50 / 100 / 250 ms, gross errors (> 500 ms), bias."""
    absolute = np.abs(errors)
    bias = float(np.median(errors))
    return {
        "syllables": int(len(errors)),
        "median_ms": float(np.median(absolute) * 1000),
        "within_50ms": float(np.mean(absolute <= 0.05) * 100),
        "within_100ms": float(np.mean(absolute <= 0.10) * 100),
        "within_250ms": float(np.mean(absolute <= 0.25) * 100),
        "gross": int(np.sum(absolute > GROSS_ERROR_SEC)),
        "gross_pct": float(np.mean(absolute > GROSS_ERROR_SEC) * 100),
        "bias_ms": bias * 1000,
        "median_ms_unbiased": float(np.median(np.abs(errors - bias)) * 1000),
    }
