"""Spectral sonification — map graph spectrum to audio.

Renders the spectral energy distribution of a community as a WAV file:
  eigenvalue → frequency (200 Hz – 4 kHz, log scale)
  energy    → amplitude

Clean community = low-band hum.  Ring community = high-band screech.
It's the same array, rendered as sound.

Stack: numpy + scipy.io.wavfile (no external audio deps).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100  # CD quality
DURATION = 3.0       # seconds per community


def _eigenvalue_to_frequency(
    eigenvalue: float,
    freq_min: float = 200.0,
    freq_max: float = 4000.0,
    lambda_max: float = 2.0,
) -> float:
    """Map eigenvalue ∈ [0, λ_max] to frequency via log scale.

    Low eigenvalues → low frequencies (bass hum).
    High eigenvalues → high frequencies (screech).
    """
    # Normalize to [0, 1]
    t = min(max(eigenvalue / lambda_max, 0.0), 1.0)
    # Log scale mapping
    return freq_min * (freq_max / freq_min) ** t


def synthesize_community(
    eigenvalues: np.ndarray,
    sed: np.ndarray,
    duration: float = DURATION,
    sample_rate: int = SAMPLE_RATE,
    fade_ms: float = 50.0,
) -> np.ndarray:
    """Synthesize a WAV signal from a community's spectral energy distribution.

    Each eigenvalue becomes a sine tone at the mapped frequency; its amplitude
    is the SED energy for that eigenvalue.  The result is the additive sum of
    all tones — a chord that encodes the community's spectral signature.
    """
    n_samples = int(duration * sample_rate)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    signal = np.zeros(n_samples, dtype=np.float64)

    for eigenvalue, energy in zip(eigenvalues, sed):
        if energy < 1e-6:
            continue
        freq = _eigenvalue_to_frequency(eigenvalue)
        amplitude = float(energy)
        # Sine tone with slight phase randomness for natural sound
        phase = np.random.uniform(0, 2 * np.pi)
        signal += amplitude * np.sin(2 * np.pi * freq * t + phase)

    # Normalize to [-1, 1]
    mx = np.abs(signal).max()
    if mx > 0:
        signal = signal / mx * 0.9

    # Apply fade-in/out to avoid clicks
    fade_samples = int(fade_ms / 1000 * sample_rate)
    if fade_samples > 0 and fade_samples < n_samples // 2:
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        signal[:fade_samples] *= fade_in
        signal[-fade_samples:] *= fade_out

    return signal


def save_wav(
    signal: np.ndarray,
    path: str | Path,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    """Save a float64 signal as a 16-bit WAV file."""
    from scipy.io import wavfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to 16-bit integer
    signal_int = (signal * 32767).astype(np.int16)
    wavfile.write(str(path), sample_rate, signal_int)

    logger.info("Saved WAV: %s (%.1f sec, %d Hz)", path, len(signal) / sample_rate, sample_rate)
    return path


def sonify_communities(
    spectral_report,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Generate WAV files for clean and ring communities.

    If spectral shift data is available, generates:
    - spectral_clean.wav  — a clean (non-anomalous) community
    - spectral_ring.wav   — a community with injected ring

    Also generates individual community WAVs for the top few.
    """
    from .config import OUTPUT_DIR

    output_dir = Path(output_dir or OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}

    # Generate WAVs for individual communities
    for cr in spectral_report.community_reports[:6]:
        signal = synthesize_community(cr.eigenvalues, cr.sed)
        label = "anomalous" if cr.has_anomaly else "normal"
        name = f"spectral_community_{cr.community_id}_{label}.wav"
        path = save_wav(signal, output_dir / name)
        outputs[f"community_{cr.community_id}"] = path

    # If we have shift data, generate clean vs ring comparison
    if spectral_report.shift_result is not None:
        sr = spectral_report.shift_result

        clean_signal = synthesize_community(sr.clean_eigenvalues, sr.clean_sed, duration=4.0)
        ring_signal = synthesize_community(sr.ring_eigenvalues, sr.ring_sed, duration=4.0)

        outputs["clean"] = save_wav(clean_signal, output_dir / "spectral_clean.wav")
        outputs["ring"] = save_wav(ring_signal, output_dir / "spectral_ring.wav")

        # Combined: clean then ring with a pause
        pause = np.zeros(int(0.5 * SAMPLE_RATE))
        combined = np.concatenate([clean_signal, pause, ring_signal])
        outputs["comparison"] = save_wav(combined, output_dir / "spectral_comparison.wav")

    logger.info("Generated %d WAV files in %s", len(outputs), output_dir)
    return outputs
