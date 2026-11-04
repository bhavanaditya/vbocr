"""Tests for the phone-photo clean-up (page flattening, shadow removal). No OCR engine needed."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from vbocr.preprocess import find_page, has_shadow, prepare  # noqa: E402


def _page(width=1200, height=800):
    """White page with dark 'text' bars."""
    page = np.full((height, width, 3), 250, np.uint8)
    for y in range(80, height - 80, 60):
        cv2.rectangle(page, (80, y), (width - 300, y + 18), (20, 20, 20), -1)
    return page


def _photo_at_angle():
    page = _page()
    h, w = page.shape[:2]
    corners = np.float32([[300, 260], [1700, 180], [1780, 1250], [220, 1350]])
    matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), corners)
    table = np.full((1500, 2000, 3), (40, 70, 110), np.uint8)
    warped = cv2.warpPerspective(page, matrix, (2000, 1500))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matrix, (2000, 1500))
    return np.where(mask[..., None] > 0, warped, table), corners


def test_page_corners_found_and_flattened():
    photo, corners = _photo_at_angle()
    found = find_page(photo)
    assert found is not None
    assert np.abs(found - corners).max() < 25
    flat, done = prepare(photo)
    assert "page flattened" in done
    assert abs(flat.shape[1] / flat.shape[0] - 1.5) < 0.15  # back to the page's 3:2 shape


def test_scan_and_screenshot_unchanged():
    page = _page()
    out, done = prepare(page)
    assert done == [] and out is page


def test_shadow_on_cropped_page_is_evened_not_cropped():
    page = _page().astype("float32")
    shaded = (page * np.linspace(0.45, 1.0, page.shape[1])[None, :, None]).astype("uint8")
    assert find_page(shaded) is None  # the bright half is not mistaken for the page
    assert has_shadow(shaded)
    out, done = prepare(shaded)
    assert done == ["shadows removed"]
    left, right = out[20:60, 20:200].mean(), out[20:60, -200:-20].mean()
    assert abs(left - right) < 15 and left > 200
    assert out[85:95, 100:200].mean() < 120  # text stays dark
