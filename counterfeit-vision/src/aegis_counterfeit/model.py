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

    def decide_verdict(self, p_fake: float, n_failed_features: int) -> str:
        if p_fake >= self.fake_threshold:
            return "fake"
        if p_fake <= self.genuine_threshold and n_failed_features == 0:
            return "genuine"
        # Everything else — mid-band CNN score, or ANY failed security
        # feature — goes to manual inspection. A note is never certified
        # genuine while a security check is failing.
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
    """Rank-based AUC (avoids a sklearn dependency in the torch module)."""
    order = np.argsort(y_score)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(y_score) + 1)
    pos = y_true == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def train(data_dir: Path, cfg: TrainConfig | None = None) -> tuple[CounterfeitModel, TrainReport]:
    cfg = cfg or TrainConfig()
    torch.manual_seed(cfg.seed)

    ds = NoteDataset(data_dir, cfg.img_size)
    n_val = max(int(len(ds) * cfg.val_fraction), 2)
    n_train = len(ds) - n_val
    train_ds, val_ds = torch.utils.data.random_split(
        ds, [n_train, n_val], generator=torch.Generator().manual_seed(cfg.seed)
    )
    train_dl = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=cfg.batch_size)

    net = build_model(cfg.backbone)
    head_params = [p for p in net.parameters() if p.requires_grad]
    opt = torch.optim.Adam(head_params, lr=cfg.lr)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(cfg.epochs):
        net.train()
        total = 0.0
        for x, y in train_dl:
            opt.zero_grad()
            loss = loss_fn(net(x), y)
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(y)
        print(f"epoch {epoch + 1}/{cfg.epochs}  train loss {total / n_train:.4f}")

    net.eval()
    probs, labels = [], []
    with torch.no_grad():
        for x, y in val_dl:
            probs.extend(torch.softmax(net(x), dim=1)[:, 1].tolist())
            labels.extend(y.tolist())
    y_true = np.array(labels)
    y_prob = np.array(probs)

    pred_fake = y_prob >= cfg.fake_threshold
    tp = int((pred_fake & (y_true == 1)).sum())
    fp = int((pred_fake & (y_true == 0)).sum())
    fn = int((~pred_fake & (y_true == 1)).sum())
    uncertain = (y_prob > cfg.genuine_threshold) & (y_prob < cfg.fake_threshold)

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
    model = CounterfeitModel(
        net=net,
        backbone=cfg.backbone,
        img_size=cfg.img_size,
        fake_threshold=cfg.fake_threshold,
        genuine_threshold=cfg.genuine_threshold,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return model, report


def save_report(report: TrainReport, path: Path = REPORT_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path
