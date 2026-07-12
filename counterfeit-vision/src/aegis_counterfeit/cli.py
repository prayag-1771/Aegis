"""Counterfeit Vision command line.

    python -m aegis_counterfeit.cli prepare-real
        Download 4,002 REAL note photos + build data/real/{genuine,fake}/.

    python -m aegis_counterfeit.cli train [--data data/real] [--backbone efficientnet_b0]
        Train the CNN on the real dataset and save weights + held-out report.

    python -m aegis_counterfeit.cli generate
        Render the synthetic training set into data/synth/ (unit tests only).

    python -m aegis_counterfeit.cli analyze path/to/note.jpg [--out out.json]
        Scan one note image; print contract JSON.

    python -m aegis_counterfeit.cli demo
        Render fresh genuine + fake notes and run them through the model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import analyze_file, analyze_image, validate_payload
from .config import DATA_DIR, MODELS_DIR, TrainConfig
from .model import META_FILE, CounterfeitModel, save_report, train
from .synth import CHECKABLE_FEATURES, NoteSpec, SynthConfig, render_note


def cmd_generate(_: argparse.Namespace) -> int:
    out = DATA_DIR / "synth"
    print(f"Rendering synthetic dataset into {out} ...")
    from .data import prepare_synth_dataset

    prepare_synth_dataset(SynthConfig())
    n = len(list(out.rglob("*.png")))
    print(f"Done: {n} images.")
    return 0


def cmd_prepare_real(_: argparse.Namespace) -> int:
    """Download real note photos and build data/real/{genuine,fake}/."""
    from .data import prepare_real_dataset

    print("Downloading real note dataset (kagglehub, ~public) and preparing ...")
    out = prepare_real_dataset()
    n = len(list(out.rglob("*.png")))
    print(f"Done: {n} images in {out}.")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    if not data_dir.exists():
        sys.exit(f"{data_dir} not found. Run: python -m aegis_counterfeit.cli generate")
    cfg = TrainConfig(backbone=args.backbone)
    model, report = train(data_dir, cfg)
    model.save()
    save_report(report)
    print(f"Weights -> {MODELS_DIR}")
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def _load_model() -> CounterfeitModel:
    if not META_FILE.exists():
        sys.exit("No trained model. Run: python -m aegis_counterfeit.cli train")
    return CounterfeitModel.load()


def cmd_analyze(args: argparse.Namespace) -> int:
    model = _load_model()
    payload = analyze_file(Path(args.image), model)
    validate_payload(payload)
    output = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote {args.out}")
    print(output)
    return 0


def cmd_demo(_: argparse.Namespace) -> int:
    model = _load_model()
    # "Rs" not "₹": Windows consoles default to cp1252 and choke on U+20B9.
    cases = [("genuine Rs500", NoteSpec(denomination="500", seed=9001)),
             ("genuine Rs2000", NoteSpec(denomination="2000", seed=9002))]
    for i, feature in enumerate(CHECKABLE_FEATURES):
        cases.append((f"fake Rs500 (no {feature})",
                      NoteSpec(denomination="500", is_fake=True,
                               missing_features=[feature], seed=9100 + i)))
    for name, spec in cases:
        payload = analyze_image(render_note(spec), model)
        validate_payload(payload)
        missing = ", ".join(payload["missing_features"]) or "-"
        print(f"[{payload['verdict']:>9}] conf={payload['confidence']:.2f} "
              f"denom={payload['denomination']:>5} missing: {missing:<35} <- {name}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="counterfeit-vision", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("generate", help="render synthetic dataset (tests)").set_defaults(fn=cmd_generate)
    sub.add_parser("prepare-real", help="download + build real dataset").set_defaults(
        fn=cmd_prepare_real
    )

    p_train = sub.add_parser("train", help="train the CNN")
    p_train.add_argument("--data", default=str(DATA_DIR / "real"))
    p_train.add_argument("--backbone", default=TrainConfig().backbone,
                         choices=["efficientnet_b0", "mobilenet_v3_small", "tiny"])
    p_train.set_defaults(fn=cmd_train)

    p_analyze = sub.add_parser("analyze", help="scan one note image")
    p_analyze.add_argument("image")
    p_analyze.add_argument("--out", default=None)
    p_analyze.set_defaults(fn=cmd_analyze)

    sub.add_parser("demo", help="scan freshly rendered demo notes").set_defaults(fn=cmd_demo)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
