"""Thin wrapper around PaddleOCR that returns Page objects."""

import logging
import os
import threading
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Page, Word

log = logging.getLogger(__name__)

# Keep the models inside the install folder (not the user profile), so the server works
# for every Windows user on the PC and offline. Must be set before paddleocr is imported.
os.environ.setdefault(
    "PADDLE_PDX_CACHE_HOME",
    str(Path(__file__).resolve().parent.parent / "models"),
)
# Skip PaddleX's online model-host check on every start; models are cached locally.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# Harmless start-up warnings that only confuse users reading the console.
warnings.filterwarnings("ignore", message=".*`lang` and `ocr_version` will be ignored.*")
warnings.filterwarnings("ignore", message=".*No ccache found.*")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS

# Photos larger than this (longest side, pixels) are scaled down before OCR. Phone cameras
# give 4000+ px images; more pixels only slow the OCR down without improving it.
MAX_IMAGE_SIDE = 4000


class OcrEngine:
    """Loads PaddleOCR once and reuses it. PaddleOCR is not thread-safe, so calls are serialised."""

    def __init__(self, options: Optional[Dict[str, Any]] = None, pdf_options: Optional[Dict[str, Any]] = None):
        self._options = dict(options or {})
        self._pdf = dict(pdf_options or {})
        self._lock = threading.Lock()
        self.mkldnn_fallback = False  # True after oneDNN failed and was switched off
        self._ocr = self._create(self._options)

    @staticmethod
    def _create(options: Dict[str, Any]) -> Any:
        from paddleocr import PaddleOCR  # imported here: loading takes a few seconds

        log.info("Loading PaddleOCR with options %s", options)
        return PaddleOCR(**options)

    def read(self, path: str) -> List[Page]:
        """Read an image or PDF. Returns one Page per image / PDF page / TIFF frame."""
        if Path(path).suffix.lower() in PDF_EXTENSIONS:
            from .pdf import read_pdf

            parts = read_pdf(
                str(path),
                use_text_layer=bool(self._pdf.get("use_text_layer", True)),
                min_characters=int(self._pdf.get("min_characters", 40)),
                render_dpi=int(self._pdf.get("render_dpi", 200)),
            )
        else:
            parts = [("image", frame) for frame in load_inputs(path)]
        pages = []
        with self._lock:
            for kind, item in parts:
                if kind == "text":
                    pages.append(item)
                else:
                    pages.extend(_to_page(result) for result in self._predict(item))
        return pages

    def _predict(self, item: Any) -> List[Any]:
        try:
            return list(self._ocr.predict(item))
        except Exception as error:  # noqa: BLE001 - PaddlePaddle raises many error types
            if "enable_mkldnn" in self._options:
                raise
            # PaddlePaddle 3.3 has a bug in its oneDNN (MKL-DNN) CPU acceleration on many
            # Intel/AMD Windows PCs: "ConvertPirAttribute2RuntimeAttribute not support ...".
            # Reload without oneDNN once and keep using that for the rest of the run.
            log.warning(
                "OCR failed (%s: %s). Retrying without oneDNN CPU acceleration. "
                "To skip this retry on every start, set 'enable_mkldnn: false' under 'ocr:' in "
                "config/settings.yaml.",
                type(error).__name__,
                _short(error),
            )
            self._options["enable_mkldnn"] = False
            self._ocr = self._create(self._options)
            self.mkldnn_fallback = True
            return list(self._ocr.predict(item))

    def self_test(self) -> int:
        """Read a small generated image to check the OCR really runs on this PC.
        Returns the number of text lines found."""
        import numpy as np
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (640, 160), "white")
        draw = ImageDraw.Draw(image)
        try:
            from PIL import ImageFont

            font = ImageFont.load_default(size=36)
        except TypeError:  # Pillow < 10.1
            font = None
        draw.text((20, 20), "INVOICE NO 12345", fill="black", font=font)
        draw.text((20, 90), "TOTAL 1335.32", fill="black", font=font)
        with self._lock:
            results = self._predict(np.asarray(image)[:, :, ::-1].copy())
        return sum(len(r["rec_texts"]) for r in results)


def load_inputs(path: str) -> List[Any]:
    """Turn a file into what PaddleOCR accepts.

    Images are opened here with Pillow instead of letting PaddleOCR read the file, because that
    handles more cases: transparent / palette / 16-bit / greyscale PNGs, phone photos that are
    stored sideways with an EXIF rotation flag, multi-page TIFFs, WEBP, and file paths with
    non-English characters on Windows. PDFs are passed to PaddleOCR as a path.
    """
    suffix = Path(path).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return [str(path)]  # OcrEngine.read handles PDFs page by page (see pdf.py)
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(
            "Unsupported file type '{}'. Supported: {}".format(
                suffix or Path(path).name, ", ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS))
            )
        )
    return _load_image_frames(path)


def _load_image_frames(path: str) -> List[Any]:
    import numpy as np
    from PIL import Image, ImageOps

    frames = []
    try:
        with Image.open(path) as image:
            count = getattr(image, "n_frames", 1) if image.format == "TIFF" else 1
            for index in range(count):
                image.seek(index)
                frame = ImageOps.exif_transpose(image) if index == 0 else image.copy()
                rgb = _to_rgb(frame)
                if max(rgb.size) > MAX_IMAGE_SIDE:
                    rgb.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
                # PaddleOCR expects OpenCV order: BGR
                frames.append(np.ascontiguousarray(np.asarray(rgb)[:, :, ::-1]))
    except (OSError, SyntaxError) as error:
        raise ValueError("Cannot read image {}: {}".format(Path(path).name, error))
    return frames


def _to_rgb(image: Any) -> Any:
    """Any Pillow image -> RGB. Transparent areas become white, not black."""
    from PIL import Image

    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        image = image.point(lambda v: v * (1 / 256)).convert("L")
    if image.mode == "P":
        image = image.convert("RGBA")
    if image.mode in ("RGBA", "LA", "PA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
        return background
    return image.convert("RGB")


def _to_page(result: Any) -> Page:
    words = [
        Word(str(text), float(score), *[float(v) for v in box])
        for text, score, box in zip(result["rec_texts"], result["rec_scores"], result["rec_boxes"])
        if str(text).strip()
    ]
    image = _page_image(result)
    height, width = image.shape[:2] if image is not None else (_extent(words, "y2"), _extent(words, "x2"))
    return Page(words=words, width=float(width), height=float(height))


def _page_image(result: Any) -> Any:
    preprocess = result.get("doc_preprocessor_res") if hasattr(result, "get") else None
    if preprocess is not None and preprocess.get("output_img") is not None:
        return preprocess["output_img"]
    return result.get("input_img") if hasattr(result, "get") else None


def _extent(words: List[Word], attr: str) -> float:
    return max((getattr(w, attr) for w in words), default=1.0)


def _short(error: Exception) -> str:
    text = str(error).strip()
    return text.splitlines()[-1][:300] if text else ""
