"""Before/after evaluation for the self-improving classifier (innovation #2).

RUN WITH THE FRAUD-SHIELD INTERPRETER (it imports aegis_fraud_shield):

    fraud-shield-nlp/.venv/Scripts/python \
        command-centre/fusion/src/aegis_fusion/self_improve_eval.py

Protocol (honest by construction):
  1. BEFORE: score the CURRENT model on the held-out LLM eval set
     (variants the model has never seen; two families are entirely new).
  2. Retrain — data.load_training_frame() now merges data/extra_corpus/
     (the *training half* of the LLM variants; the eval half never enters).
  3. AFTER: score the RETRAINED model on the SAME eval set.

"Caught" = verdict in (scam, suspicious). Legit correctness = verdict == legit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
FUSION_ROOT = HERE.parents[2]
REPO_ROOT = FUSION_ROOT.parents[1]
EVAL_SET = FUSION_ROOT / "output" / "llm_eval_set.json"
REPORT = FUSION_ROOT / "output" / "self_improve_report.json"


def score(model, rows: list[dict]) -> dict:
    from aegis_fraud_shield.analyze import analyze

    per_family: dict[str, list[bool]] = {}
    for row in rows:
        verdict = analyze(row["text"], model)["verdict"]
        if row["label"] == 1:
            ok = verdict in ("scam", "suspicious")
        else:
            ok = verdict == "legit"
        per_family.setdefault(row["origin"], []).append(ok)

    scam_rows = [r for r in rows if r["label"] == 1]
    legit_rows = [r for r in rows if r["label"] == 0]

    def _rate(subset: list[dict]) -> float:
        oks = []
        for r in subset:
            v = analyze(r["text"], model)["verdict"]
            oks.append(v in ("scam", "suspicious") if r["label"] == 1 else v == "legit")
        return round(sum(oks) / len(oks), 4) if oks else 0.0

    return {
        "scam_recall": _rate(scam_rows),
        "legit_accuracy": _rate(legit_rows),
        "by_family": {
            fam: round(sum(oks) / len(oks), 4) for fam, oks in sorted(per_family.items())
        },
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import aegis_fraud_shield.data as fs_data
    from aegis_fraud_shield.data import load_extra_corpus, load_training_frame
    from aegis_fraud_shield.model import save_report, train

    rows = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    print(f"eval set: {len(rows)} held-out LLM-generated messages")

    extra = load_extra_corpus()
    assert extra is not None and len(extra) > 0, (
        "no extra corpus found — run `python -m aegis_fusion.self_improve` first"
    )

    # BEFORE: baseline trained fresh WITHOUT augmentation — self-contained
    # protocol, immune to whatever model happens to be on disk from prior runs.
    print("training BASELINE (UCI + templates only) ...")
    real_loader = fs_data.load_extra_corpus
    fs_data.load_extra_corpus = lambda: None  # temporarily disable the hook
    try:
        baseline_clf, _ = train(load_training_frame())
    finally:
        fs_data.load_extra_corpus = real_loader

    print("BEFORE — baseline model vs unseen LLM variants:")
    before = score(baseline_clf, rows)
    print(json.dumps(before, indent=2))

    print(f"retraining with +{len(extra)} LLM-augmented rows (balanced) ...")
    clf, report = train(load_training_frame())
    clf.save()
    save_report(report)

    print("AFTER — retrained model vs the SAME eval set:")
    after = score(clf, rows)
    print(json.dumps(after, indent=2))

    REPORT.write_text(
        json.dumps(
            {
                "protocol": "eval half never trained on; two families brand-new to the model",
                "n_eval": len(rows),
                "n_augmentation_rows": int(len(extra)),
                "before": before,
                "after": after,
                "held_out_roc_auc_after": report.to_dict().get("roc_auc"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
