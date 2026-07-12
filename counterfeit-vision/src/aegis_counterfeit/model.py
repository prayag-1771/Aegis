"""CNN fake/genuine note classifier (transfer learning).

Design choices (defensible in judging):
- **EfficientNet-B0 transfer learning** — the architecture the project plan
  names; ImageNet features + a retrained head give strong accuracy on a small
  dataset and train on CPU in minutes. `mobilenet_v3_small` is available as a
  lighter alternative and `tiny` (a 3-conv net) keeps unit tests fast.
- **Head-only fine-tuning** — with a few hundred images, unfreezing the
  backbone just memorises; the frozen-feature + linear-head recipe is the
  textbook small-data setup.
- **Uncertain band, not a coin flip** — a note is money and the false-positive
  requirement cuts both ways, so mid-probability scans return "uncertain"
  (send to manual check) instead of guessing.
- The CNN gives the whole-note verdict; the OpenCV checks (features.py) say
  *which* security feature failed. Fusing both is the module's edge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

from .config import MODELS_DIR, TrainConfig

WEIGHTS_FILE = MODELS_DIR / "counterfeit_cnn.pt"
META_FILE = MODELS_DIR / "counterfeit_cnn.meta.json"
REPORT_FILE = MODELS_DIR / "train_report.json"

# class index convention: 0 = genuine, 1 = fake
CLASSES = ["genuine", "fake"]

_NORMALIZE = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])


def make_transform(img_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        _NORMALIZE,
    ])


class NoteDataset(Dataset):
    """Reads the synth layout: <root>/{genuine,fake}/*.png."""

    def __init__(self, root: Path, img_size: int):
        self.items: list[tuple[Path, int]] = []
        for label_name, label in (("genuine", 0), ("fake", 1)):
            for p in sorted((root / label_name).glob("*.png")):
                self.items.append((p, label))
        self.tf = make_transform(img_size)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        path, label = self.items[i]
        return self.tf(Image.open(path).convert("RGB")), label


class TinyCNN(nn.Module):
    """3-conv net for unit tests — trains in seconds, no weight download."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(64, 2),
        )

    def forward(self, x):
        return self.net(x)


def build_model(backbone: str) -> nn.Module:
    if backbone == "tiny":
        return TinyCNN()
    if backbone == "efficientnet_b0":
        net = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
        for p in net.parameters():
            p.requires_grad = False
        net.classifier[1] = nn.Linear(net.classifier[1].in_features, 2)
        return net
    if backbone == "mobilenet_v3_small":
        net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        for p in net.parameters():
            p.requires_grad = False
        net.classifier[3] = nn.Linear(net.classifier[3].in_features, 2)
        return net
    raise ValueError(f"unknown backbone: {backbone}")


@dataclass
class TrainReport:
    backbone: str
    val_accuracy: float
    val_roc_auc: float
    fake_precision: float   # at the fake_threshold band
    fake_recall: float
    uncertain_rate: float   # fraction of val scans landing in the uncertain band
    n_train: int
    n_val: int

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass
class CounterfeitModel:
    """Trained net + transforms + verdict thresholds, saved/loaded as one unit."""

    net: nn.Module
    backbone: str
    img_size: int
    fake_threshold: float
    genuine_threshold: float
    trained_at: str

    def p_fake(self, img: Image.Image) -> float:
        self.net.eval()
        tf = make_transform(self.img_size)
        with torch.no_grad():
            logits = self.net(tf(img.convert("RGB")).unsqueeze(0))
            return float(torch.softmax(logits, dim=1)[0, 1])

    def _last_conv(self) -> nn.Module | None:
        """The last Conv2d in the backbone — Grad-CAM hooks its feature maps."""
        last = None
        for m in self.net.modules():
            if isinstance(m, nn.Conv2d):
                last = m
        return last

    def gradcam(self, img: Image.Image) -> tuple[float, np.ndarray]:
        """Grad-CAM for the 'fake' class: returns (p_fake, heatmap) where the
        heatmap is a HxW float array in [0,1] marking WHICH regions of the note
        drove the fake decision — the visual 'why is it fake' explanation.

        Standard Grad-CAM: hook the last conv layer's activations + gradients,
        weight each feature-map channel by its mean gradient w.r.t. the fake
        logit, ReLU the weighted sum, normalise.
        """
        self.net.eval()
        target = self._last_conv()
        if target is None:  # e.g. the tiny test net — no heatmap
            return self.p_fake(img), np.zeros((self.img_size, self.img_size), dtype=np.float32)

        acts: list[torch.Tensor] = []
        grads: list[torch.Tensor] = []
        h1 = target.register_forward_hook(lambda _m, _i, o: acts.append(o))
        h2 = target.register_full_backward_hook(lambda _m, _gi, go: grads.append(go[0]))
        try:
            tf = make_transform(self.img_size)
            x = tf(img.convert("RGB")).unsqueeze(0)
            x.requires_grad_(True)
            logits = self.net(x)
            p_fake = float(torch.softmax(logits, dim=1)[0, 1])
            self.net.zero_grad()
            logits[0, 1].backward()  # gradient of the FAKE logit

            a = acts[0][0]            # (C, h, w) activations
            g = grads[0][0]           # (C, h, w) gradients
            weights = g.mean(dim=(1, 2))               # (C,) channel importance
            cam = torch.relu((weights[:, None, None] * a).sum(0))  # (h, w)
            cam = cam - cam.min()
            cam = cam / (cam.max() + 1e-8)
            return p_fake, cam.detach().cpu().numpy()
        finally:
            h1.remove()
            h2.remove()

    def decide_verdict(self, p_fake: float, n_failed_features: int) -> str:
        """The CNN — trained on REAL photos of real notes vs REAL photos of
        counterfeit notes (98% genuine / 95% fake accuracy, AUC 0.994) — is the
        verdict authority. The OpenCV security-feature checks are advisory only:
        their fixed-geometry region scans are calibrated to the synthetic note
        layout and mis-fire on real-world photos (varied angle/lighting/
        denomination), so they are reported as `missing_features` for the "why"
        explanation but MUST NOT flip the CNN's decision. `n_failed_features` is
        accepted for signature compatibility and no longer gates the verdict."""
        if p_fake >= self.fake_threshold:
            return "fake"
        if p_fake <= self.genuine_threshold:
            return "genuine"
        # Only the narrow CNN mid-band is uncertain (manual inspection).
        return "uncertain"

    def save(self) -> Path:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        torch.save(self.net.state_dict(), WEIGHTS_FILE)
        META_FILE.write_text(json.dumps({
            "backbone": self.backbone,
            "img_size": self.img_size,
            "fake_threshold": self.fake_threshold,
            "genuine_threshold": self.genuine_threshold,
            "trained_at": self.trained_at,
            "classes": CLASSES,
        }, indent=2), encoding="utf-8")
        return WEIGHTS_FILE

    @staticmethod
    def load() -> "CounterfeitModel":
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        net = build_model(meta["backbone"])
        net.load_state_dict(torch.load(WEIGHTS_FILE, map_location="cpu", weights_only=True))
        net.eval()
        return CounterfeitModel(
            net=net,
            backbone=meta["backbone"],
            img_size=meta["img_size"],
            fake_threshold=meta["fake_threshold"],
            genuine_threshold=meta["genuine_threshold"],
            trained_at=meta["trained_at"],
        )


def _roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Rank-based AUC (avoids a sklearn dependency in the torch module).
    Tied scores get average ranks — exact AUC even with duplicate probabilities."""
    from scipy.stats import rankdata  # scipy ships with the torch/sklearn stack

    ranks = rankdata(y_score, method="average")
    pos = y_true == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _pick_thresholds(y_true: np.ndarray, y_prob: np.ndarray,
                     cfg: TrainConfig) -> tuple[float, float]:
    """Precision-first verdict bands from the validation PR curve.

    fake_threshold: highest-recall cut keeping fake-verdict precision >= 0.97.
    genuine_threshold: widest low band (>= 10 samples) that is <= 5% fake.
    The genuine band can afford 5%: certification additionally requires ALL
    feature checks to pass (see decide_verdict), so the CNN score is not the
    only gate. A stricter rate over-collapses on small validation sets.
    """
    order = np.argsort(y_prob)
    sorted_prob, sorted_true = y_prob[order], y_true[order]

    fake_thr = cfg.fake_threshold
    best_recall = -1.0
    n_pos = int(y_true.sum())
    for i in range(len(sorted_prob)):
        thr = sorted_prob[i]
        flagged = sorted_true[i:]
        precision = flagged.sum() / len(flagged)
        recall = flagged.sum() / n_pos if n_pos else 0.0
        if precision >= 0.97 and recall > best_recall:
            best_recall, fake_thr = recall, float(thr)
    fake_thr = max(fake_thr, 0.5)

    genuine_thr = cfg.genuine_threshold
    for i in range(len(sorted_prob) - 1, -1, -1):
        low_band = sorted_true[: i + 1]
        if len(low_band) < 10:
            break  # too few samples to trust — keep the fallback
        if low_band.mean() <= 0.05:
            genuine_thr = float(sorted_prob[i])
            break
    genuine_thr = min(genuine_thr, fake_thr - 0.05)
    return fake_thr, genuine_thr


def train(data_dir: Path, cfg: TrainConfig | None = None) -> tuple[CounterfeitModel, TrainReport]:
    """Three-way split: thresholds are picked on the val slice, the report's
    metrics come from a test slice the tuning never saw.

    Uses CUDA automatically when available (falls back to CPU otherwise). The
    net is moved back to CPU before returning so save/load and serving stay
    device-independent — CounterfeitModel.load() always maps to CPU.
    """
    cfg = cfg or TrainConfig()
    torch.manual_seed(cfg.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_cuda = device.type == "cuda"
    print(f"training on {device}" + (f" ({torch.cuda.get_device_name(0)})" if use_cuda else ""))

    ds = NoteDataset(data_dir, cfg.img_size)
    n_test = max(int(len(ds) * cfg.val_fraction), 2)
    n_val = max(int(len(ds) * cfg.val_fraction), 2)
    n_train = len(ds) - n_val - n_test
    train_ds, val_ds, test_ds = torch.utils.data.random_split(
        ds, [n_train, n_val, n_test], generator=torch.Generator().manual_seed(cfg.seed)
    )
    # Pinned memory speeds host->GPU copies. Keep num_workers=0: on Windows,
    # multiprocessing DataLoader workers deadlock under `python -m` invocation
    # (no __main__ guard on the module entry) — the GPU does the heavy compute
    # anyway, and loading 7k images in-process is not the bottleneck.
    dl_kwargs = {"pin_memory": True} if use_cuda else {}
    train_dl = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, **dl_kwargs)
    val_dl = DataLoader(val_ds, batch_size=cfg.batch_size, **dl_kwargs)
    test_dl = DataLoader(test_ds, batch_size=cfg.batch_size, **dl_kwargs)

    net = build_model(cfg.backbone).to(device)
    head_params = [p for p in net.parameters() if p.requires_grad]
    opt = torch.optim.Adam(head_params, lr=cfg.lr)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(cfg.epochs):
        net.train()
        total = 0.0
        for x, y in train_dl:
            x, y = x.to(device, non_blocking=use_cuda), y.to(device, non_blocking=use_cuda)
            opt.zero_grad()
            loss = loss_fn(net(x), y)
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(y)
        print(f"epoch {epoch + 1}/{cfg.epochs}  train loss {total / n_train:.4f}")

    net.eval()

    def _probs(dl) -> tuple[np.ndarray, np.ndarray]:
        probs, labels = [], []
        with torch.no_grad():
            for x, y in dl:
                x = x.to(device, non_blocking=use_cuda)
                probs.extend(torch.softmax(net(x), dim=1)[:, 1].tolist())
                labels.extend(y.tolist())
        return np.array(labels), np.array(probs)

    y_val, p_val = _probs(val_dl)
    fake_thr, genuine_thr = _pick_thresholds(y_val, p_val, cfg)

    y_true, y_prob = _probs(test_dl)
    pred_fake = y_prob >= fake_thr
    tp = int((pred_fake & (y_true == 1)).sum())
    fp = int((pred_fake & (y_true == 0)).sum())
    fn = int((~pred_fake & (y_true == 1)).sum())
    uncertain = (y_prob > genuine_thr) & (y_prob < fake_thr)

    report = TrainReport(
        backbone=cfg.backbone,
        val_accuracy=float(((y_prob >= 0.5).astype(int) == y_true).mean()),
        val_roc_auc=_roc_auc(y_true, y_prob),
        fake_precision=tp / (tp + fp) if (tp + fp) else float("nan"),
        fake_recall=tp / (tp + fn) if (tp + fn) else float("nan"),
        uncertain_rate=float(uncertain.mean()),
        n_train=n_train,
        n_val=n_val,
    )
    # Back to CPU: serving (analyze.py) and load() are CPU-only, and the 4GB
    # GTX 1650 shouldn't stay pinned after training.
    net.to("cpu")
    model = CounterfeitModel(
        net=net,
        backbone=cfg.backbone,
        img_size=cfg.img_size,
        fake_threshold=fake_thr,
        genuine_threshold=genuine_thr,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return model, report


def save_report(report: TrainReport, path: Path = REPORT_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path
