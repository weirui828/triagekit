import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ..preprocess import preprocess
from ..schemas import PreprocessingConfig
from .base import TextClassifier


class TfidfLr(TextClassifier):
    kind = "tfidf_lr"

    def _prep(self, texts: list[str]) -> list[str]:
        return [preprocess(t, self.preprocessing) for t in texts]

    def fit(self, texts, labels, val_texts=None, val_labels=None):
        p = self.params
        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, p.get("ngram_max", 2)), min_df=p.get("min_df", 1),
                                      max_features=p.get("max_features"), sublinear_tf=True)),
            ("lr", LogisticRegression(C=p.get("C", 1.0), max_iter=2000, random_state=self.seed,
                                      class_weight=None if p.get("class_weight") == "none" else "balanced")),
        ])
        self.pipeline.fit(self._prep(texts), labels)  # vocabulary/idf fit on training data only

    def predict_proba(self, texts):
        return self.pipeline.predict_proba(self._prep(texts))[:, 1]

    def save(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, path / "pipeline.joblib")
        (path / "meta.json").write_text(json.dumps({"kind": self.kind, "params": self.params, "seed": self.seed,
                                                   "device": self.device, "preprocessing": self.preprocessing.model_dump()}))

    @classmethod
    def load(cls, path: Path):
        meta = json.loads((path / "meta.json").read_text())
        m = cls(meta["params"], PreprocessingConfig(**meta["preprocessing"]), meta["seed"], meta["device"])
        m.pipeline = joblib.load(path / "pipeline.joblib")
        return m
