import re

from .schemas import PreprocessingConfig

_WS = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+")


def preprocess(text: str, cfg: PreprocessingConfig) -> str:
    """Applied identically at training and inference; stateless by design."""
    t = text
    if cfg.strip_urls:
        t = _URL.sub(" ", t)
    if cfg.lowercase:
        t = t.lower()
    if cfg.collapse_whitespace:
        t = _WS.sub(" ", t).strip()
    return t[: cfg.max_chars]
