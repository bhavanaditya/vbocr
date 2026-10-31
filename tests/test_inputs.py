"""Tests for image loading (PNG variants, EXIF rotation, TIFF pages) and input expansion.

No OCR engine needed: python -m pytest tests
"""

import numpy as np
import pytest
from PIL import Image

from vbocr.cli import _save_mkldnn_off, expand_inputs
from vbocr.engine import load_inputs


def _invoice_like(size=(300, 100)):
    """White page with a black bar: easy to check orientation and colours."""
    image = Image.new("RGB", size, "white")
    image.paste((0, 0, 0), (20, 20, 120, 40))
    return image


def test_transparent_png_gets_white_background(tmp_path):
    rgba = Image.new("RGBA", (50, 20), (0, 0, 0, 0))  # fully transparent black
    rgba.paste((0, 0, 0, 255), (10, 5, 20, 15))       # opaque black text
    path = tmp_path / "shot.png"
    rgba.save(path)
    (frame,) = load_inputs(str(path))
    assert frame.shape == (20, 50, 3)
    assert frame[0, 0].tolist() == [255, 255, 255]   # background white, not black
    assert frame[10, 15].tolist() == [0, 0, 0]


@pytest.mark.parametrize("mode", ["P", "L", "LA", "I;16", "CMYK"])
def test_png_modes(tmp_path, mode):
    image = _invoice_like()
    if mode == "I;16":
        image = Image.fromarray(np.asarray(image.convert("L")).astype("uint16") * 257)
    elif mode == "P":
        image = image.convert("P", palette=Image.ADAPTIVE)
    else:
        image = image.convert(mode)
    path = tmp_path / ("x.tif" if mode == "CMYK" else "x.png")
    image.save(path)
    (frame,) = load_inputs(str(path))
    assert frame.shape == (100, 300, 3) and frame.dtype == np.uint8
    assert frame[5, 5].tolist() == [255, 255, 255]
    assert frame[30, 50].max() < 30


def test_exif_rotated_photo_is_turned_upright(tmp_path):
    upright = _invoice_like()
    stored = upright.rotate(90, expand=True)  # how a phone stores a sideways photo
    exif = Image.Exif()
    exif[0x0112] = 6                           # "rotate 90° clockwise to display"
    path = tmp_path / "photo.jpg"
    stored.save(path, exif=exif)
    (frame,) = load_inputs(str(path))
    assert frame.shape[:2] == (100, 300)


def test_multi_page_tiff_gives_one_frame_per_page(tmp_path):
    path = tmp_path / "scan.tiff"
    _invoice_like().save(path, save_all=True, append_images=[_invoice_like(), _invoice_like()])
    assert len(load_inputs(str(path))) == 3


def test_large_photo_is_scaled_down(tmp_path):
    path = tmp_path / "big.jpg"
    _invoice_like((5000, 2500)).save(path)
    (frame,) = load_inputs(str(path))
    assert max(frame.shape[:2]) == 4000


def test_pdf_passed_as_path_and_bad_files_rejected(tmp_path):
    assert load_inputs(str(tmp_path / "a.pdf")) == [str(tmp_path / "a.pdf")]
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_inputs(str(tmp_path / "notes.txt"))
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Cannot read image broken.png"):
        load_inputs(str(broken))


def test_expand_inputs_folders_wildcards_and_missing(tmp_path):
    for name in ["b.PNG", "a.jpg", "c.pdf", "notes.txt"]:
        (tmp_path / name).write_bytes(b"x")
    files, has_folder, missing = expand_inputs([str(tmp_path)])
    assert [p.split("/")[-1].split("\\")[-1] for p in files] == ["a.jpg", "b.PNG", "c.pdf"]
    assert has_folder and not missing

    files, has_folder, missing = expand_inputs([str(tmp_path / "*.jpg"), str(tmp_path / "a.jpg"), "nope.png"])
    assert len(files) == 1 and not has_folder and missing == ["nope.png"]


def test_save_mkldnn_off_keeps_comments(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("server:\n  port: 5000\n\nocr:\n  # model\n  lang: en\n  # enable_mkldnn: false\n", encoding="utf-8")
    _save_mkldnn_off(path)
    _save_mkldnn_off(path)  # running install twice must not add it twice
    text = path.read_text(encoding="utf-8")
    assert text.count("\n  enable_mkldnn: false") == 1
    assert "# model" in text and "# enable_mkldnn: false" in text
