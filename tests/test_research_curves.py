"""Research representation and distance kernels (no optional deps needed)."""

from __future__ import annotations

import numpy as np
import pytest

from nanopore.fingerprint.research import curves


def test_known_shape_distances_are_ordered():
    platform = curves.make_known_shape("platform", n=80)
    flat = curves.make_known_shape("flat", n=80)
    spike = curves.make_known_shape("spike", n=80)

    for name in ("dtw", "frechet"):
        same = curves.dist(name, platform, platform)
        near_flat = curves.dist(name, platform, flat)
        near_spike = curves.dist(name, platform, spike)
        assert same == pytest.approx(0.0, abs=1e-12)
        assert near_flat > same
        assert near_spike > same


def test_dtw_and_frechet_agree_on_the_synthetic_pair_order():
    shape = curves.make_known_shape("step", n=60)
    noisy = curves.make_known_shape("step", n=60, seed_noise=0.02,
                                    rng=np.random.default_rng(0))
    other = curves.make_known_shape("bump", n=60)
    d_dtw = [curves.dtw(shape, noisy), curves.dtw(shape, other)]
    d_fr = [curves.discrete_frechet(shape, noisy),
            curves.discrete_frechet(shape, other)]
    assert (d_dtw[0] < d_dtw[1]) == (d_fr[0] < d_fr[1])


def test_dba_of_identical_shapes_returns_the_shape():
    shape = curves.make_known_shape("platform", n=50)
    center = curves.dba([shape, shape, shape], n_iter=3)
    assert center.shape == shape.shape
    assert np.allclose(center, shape, atol=1e-9)


def test_represent_r1_keeps_amplitude_and_r2_normalizes_range():
    body = np.r_[np.full(20, 100.0), np.full(20, 60.0)]
    r1 = curves.represent(body, 100.0, 25_000.0, mode="R1")
    r2 = curves.represent(body, 100.0, 25_000.0, mode="R2")
    assert r1.shape == (40, 2)
    assert r1[:, 1].max() - r1[:, 1].min() == pytest.approx(0.4)
    assert r2[:, 1].max() - r2[:, 1].min() == pytest.approx(1.0)


def test_phase_randomization_preserves_the_amplitude_spectrum():
    rng = np.random.default_rng(0)
    body = rng.normal(0.0, 1.0, 512) + np.sin(np.linspace(0, 12, 512))
    from nanopore.fingerprint.research.nulls import phase_randomize

    out = phase_randomize(body, rng)
    assert out.size == body.size
    assert float(out.mean()) == pytest.approx(float(body.mean()), abs=1e-9)
    a = np.abs(np.fft.rfft(body - body.mean()))
    b = np.abs(np.fft.rfft(out - out.mean()))
    assert np.allclose(a[1:], b[1:], rtol=1e-9, atol=1e-9)
