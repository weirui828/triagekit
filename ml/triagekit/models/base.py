from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from ..schemas import ModelKind, PreprocessingConfig


class TextClassifier(ABC):
    kind: ModelKind
    checkpoint: str | None = None

    def __init__(self, params: dict, preprocessing: PreprocessingConfig, seed: int, device: str):
        self.params, self.preprocessing, self.seed, self.device = params, preprocessing, seed, device

    @abstractmethod
    def fit(self, texts: list[str], labels: np.ndarray, val_texts: list[str] | None = None, val_labels: np.ndarray | None = None) -> None:
        """Validation data may be used for epoch/checkpoint selection only, never for fitting."""

    @abstractmethod
    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """P(label=1) per text, already preprocessed identically to training."""

    @abstractmethod
    def save(self, path: Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: Path) -> "TextClassifier": ...


def get_model(kind: ModelKind, params: dict, preprocessing: PreprocessingConfig, seed: int, device: str) -> TextClassifier:
    if kind == "tfidf_lr":
        from .tfidf_lr import TfidfLr
        return TfidfLr(params, preprocessing, seed, device)
    if kind in ("distilbert", "bertweet"):
        from .distilbert import DistilbertClassifier
        m = DistilbertClassifier(params, preprocessing, seed, device)
        m.kind = kind
        return m
    raise NotImplementedError(f"unknown model {kind}")


def load_model(kind: ModelKind, path: Path) -> TextClassifier:
    if kind == "tfidf_lr":
        from .tfidf_lr import TfidfLr
        return TfidfLr.load(path)
    if kind in ("distilbert", "bertweet"):
        from .distilbert import DistilbertClassifier
        m = DistilbertClassifier.load(path)
        m.kind = kind
        return m
    raise NotImplementedError(kind)
