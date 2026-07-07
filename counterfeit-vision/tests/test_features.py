"""Feature checks validated against the renderer's per-feature ground truth."""

import cv2
import numpy as np
import pytest

from aegis_counterfeit.features import (
    infer_denomination,
    missing_features,
    run_all_checks,
)
from aegis_counterfeit.synth import CHECKABLE_FEATURES, NoteSpec, render_note


def to_bgr(pil_img) -> np.ndarray:
    return cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)


@pytest.mark.parametrize("denom", ["500", "2000"])
def test_genuine_notes_pass_all_checks(denom):
    for seed in range(10):
        bgr = to_bgr(render_note(NoteSpec(denomination=denom, seed=seed)))
        assert missing_features(bgr) == [], f"genuine {denom} seed {seed} flagged"


@pytest.mark.parametrize("feature", CHECKABLE_FEATURES)
def test_each_missing_feature_is_detected(feature):
    for seed in range(60, 70):
        spec = NoteSpec(denomination="500", is_fake=True,
                        missing_features=[feature], seed=seed)
        detected = missing_features(to_bgr(render_note(spec)))
        assert feature in detected, f"{feature} not caught at seed {seed}"


def test_checks_report_scores_and_thresholds():
    bgr = to_bgr(render_note(NoteSpec(seed=3)))
    for check in run_all_checks(bgr):
        assert check.feature in CHECKABLE_FEATURES
        assert check.detail
        assert isinstance(check.score, float)


def test_denomination_inference():
    assert infer_denomination(to_bgr(render_note(NoteSpec(denomination="500", seed=5)))) == "500"
    assert infer_denomination(to_bgr(render_note(NoteSpec(denomination="2000", seed=6)))) == "2000"
