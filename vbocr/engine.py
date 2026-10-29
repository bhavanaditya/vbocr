"""Thin wrapper around PaddleOCR that returns Page objects."""

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from .models import Page, Word

log = logging.getLogger(__name__)

# Skip PaddleX's online model-host check on every start; models are cached locally.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class OcrEngine:
    """Loads PaddleOCR once and reuses it. PaddleOCR is not thread-safe, so calls are serialised."""

    def __init__(self, options: Optional[Dict[str, Any]] = None):
        from paddleocr import PaddleOCR  # imported here: loading takes a few seconds

        self._options = dict(options or {})
        log.info("Loading PaddleOCR with options %s", self._options)
        self._ocr = PaddleOCR(**self._options)
        self._lock = threading.Lock()

    def read(self, path: str) -> List[Page]:
        """Read an image or PDF. Returns one Page per image / PDF page."""
        with self._lock:
            results = self._ocr.predict(path)
        pages = []
        for result in results:
            words = [
                Word(str(text), float(score), *[float(v) for v in box])
                for text, score, box in zip(result["rec_texts"], result["rec_scores"], result["rec_boxes"])
                if str(text).strip()
            ]
            image = _page_image(result)
            height, width = (image.shape[:2] if image is not None else (_extent(words, "y2"), _extent(words, "x2")))
            pages.append(Page(words=words, width=float(width), height=float(height)))
        return pages


def _page_image(result: Any) -> Any:
    preprocess = result.get("doc_preprocessor_res") if hasattr(result, "get") else None
    if preprocess is not None and preprocess.get("output_img") is not None:
        return preprocess["output_img"]
    return result.get("input_img") if hasattr(result, "get") else None


def _extent(words: List[Word], attr: str) -> float:
    return max((getattr(w, attr) for w in words), default=1.0)
