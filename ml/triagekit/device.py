def resolve_device(requested: str = "auto") -> str:
    """CUDA > MPS > CPU unless overridden. TF-IDF ignores the result but records it."""
    if requested != "auto":
        return requested
    try:
        import torch  # optional until milestone 2
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
