"""DistilBERT fine-tuning. Mirrors human-loop/src/distilbert_utils.py::fine_tune so replication is like-for-like."""
import json
import random
import time
from pathlib import Path

import numpy as np

from ..preprocess import preprocess
from ..schemas import PreprocessingConfig
from .base import TextClassifier


def _torch():
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as e:
        raise RuntimeError("DistilBERT needs the 'encoders' extra: uv sync --extra encoders") from e
    return torch, AutoModelForSequenceClassification, AutoTokenizer


def _sync(torch, device: str):
    if device == "mps":
        torch.mps.synchronize()
    elif device == "cuda":
        torch.cuda.synchronize()


class DistilbertClassifier(TextClassifier):
    kind = "distilbert"

    def __init__(self, params, preprocessing, seed, device):
        super().__init__(params, preprocessing, seed, device)
        self.checkpoint = params.get("checkpoint", "distilbert-base-uncased")
        self.history: list[dict] = []
        self.best_epoch: int | None = None
        self.log = print

    def _prep(self, texts):
        return [preprocess(str(t), self.preprocessing) for t in texts]

    def _loader(self, torch, texts, labels, batch_size, shuffle):
        from torch.utils.data import DataLoader
        tok, max_len = self.tokenizer, self.params.get("max_length", 128)

        def collate(batch):
            bt, bl = zip(*batch)
            enc = tok(list(bt), padding=True, truncation=True, max_length=max_len, return_tensors="pt")
            enc["labels"] = torch.tensor(bl, dtype=torch.long)
            return enc

        pairs = [(t, int(y)) for t, y in zip(texts, labels)]
        g = torch.Generator(); g.manual_seed(self.seed)
        return DataLoader(pairs, batch_size=batch_size, shuffle=shuffle, collate_fn=collate, generator=g if shuffle else None)

    def fit(self, texts, labels, val_texts=None, val_labels=None):
        torch, AutoModel, AutoTokenizer = _torch()
        p = self.params
        random.seed(self.seed); np.random.seed(self.seed); torch.manual_seed(self.seed)
        dev = torch.device(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(self.checkpoint)
        self.model = AutoModel.from_pretrained(self.checkpoint, num_labels=2).to(dev)
        texts, labels = self._prep(texts), np.asarray(labels, dtype=int)
        train_loader = self._loader(torch, texts, labels, p.get("batch_size", 16), shuffle=True)
        epochs = p.get("epochs", 4)
        opt = torch.optim.AdamW(self.model.parameters(), lr=p.get("learning_rate", 3e-5), weight_decay=p.get("weight_decay", 0.01))
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=p.get("learning_rate", 3e-5), total_steps=len(train_loader) * epochs,
                                                    pct_start=p.get("warmup_ratio", 0.1), anneal_strategy="linear")
        weight = None
        if p.get("class_weighted_loss", True):
            counts = np.bincount(labels, minlength=2).astype(float)
            weight = torch.tensor(len(labels) / (2.0 * np.maximum(counts, 1.0)), dtype=torch.float, device=dev)
        loss_fn = torch.nn.CrossEntropyLoss(weight=weight)
        has_val = val_texts is not None and len(val_texts) > 0
        best_f1, best_state, self.best_epoch = -1.0, None, None
        t0 = time.perf_counter()
        for epoch in range(1, epochs + 1):
            self.model.train()
            running, te = 0.0, time.perf_counter()
            for batch in train_loader:
                batch = {k: v.to(dev) for k, v in batch.items()}
                y = batch.pop("labels")
                loss = loss_fn(self.model(**batch).logits, y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), p.get("grad_clip_norm", 1.0))
                opt.step(); sched.step(); opt.zero_grad()
                running += loss.item()
            _sync(torch, self.device)
            rec = {"epoch": epoch, "train_loss": round(running / len(train_loader), 4), "epoch_sec": round(time.perf_counter() - te, 1)}
            if has_val:
                from ..evaluate import macro_f1
                pv = self.predict_proba(val_texts)
                f1 = macro_f1(np.asarray(val_labels, dtype=int), (pv >= 0.5).astype(int))
                rec["val_macro_f1"] = None if f1 is None else round(float(f1), 4)
                # epoch selection reads validation at threshold 0.5, as in the original protocol; never the test set
                if f1 is not None and f1 > best_f1:
                    best_f1, self.best_epoch = float(f1), epoch
                    best_state = {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}
            self.history.append(rec)
            self.log(f"epoch {epoch}/{epochs} loss={rec['train_loss']} val_macro_f1={rec.get('val_macro_f1')} {rec['epoch_sec']}s")
        if best_state is not None:
            self.model.load_state_dict(best_state); self.model.to(dev)
        self.train_seconds = round(time.perf_counter() - t0, 1)

    def predict_proba(self, texts):
        torch, _, _ = _torch()
        dev = torch.device(self.device)
        self.model.eval()
        loader = self._loader(torch, self._prep(texts), np.zeros(len(texts), dtype=int), self.params.get("batch_size", 16) * 2, shuffle=False)
        out = []
        with torch.no_grad():
            for batch in loader:
                batch = {k: v.to(dev) for k, v in batch.items()}
                batch.pop("labels", None)
                logits = self.model(**batch).logits
                out.append(torch.softmax(logits.float(), dim=-1)[:, 1].cpu().numpy())
        return np.concatenate(out) if out else np.array([])

    def save(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(path / "hf")
        self.tokenizer.save_pretrained(path / "hf")
        (path / "meta.json").write_text(json.dumps({"kind": self.kind, "params": self.params, "seed": self.seed, "device": self.device,
                                                   "preprocessing": self.preprocessing.model_dump(), "checkpoint": self.checkpoint,
                                                   "history": self.history, "best_epoch": self.best_epoch}))

    @classmethod
    def load(cls, path: Path):
        torch, AutoModel, AutoTokenizer = _torch()
        from ..device import resolve_device
        meta = json.loads((path / "meta.json").read_text())
        m = cls(meta["params"], PreprocessingConfig(**meta["preprocessing"]), meta["seed"], resolve_device("auto"))
        m.tokenizer = AutoTokenizer.from_pretrained(path / "hf")
        m.model = AutoModel.from_pretrained(path / "hf").to(torch.device(m.device)).eval()
        m.history, m.best_epoch = meta.get("history", []), meta.get("best_epoch")
        return m
