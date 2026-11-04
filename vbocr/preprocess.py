"""Clean up phone photos before OCR: flatten the page and remove shadows.

Both steps only act when they are needed, so scans, screenshots and already cropped photos
pass through unchanged:

- flatten_page: finds the four corners of the paper (a photo taken at an angle, with the table
  or floor around it), and warps the page to a straight, flat rectangle.
- remove_shadows: evens out the background when one part of the page is much darker than
  another (shadow of the phone or hand, lamp on one side).

Images are numpy arrays in OpenCV (BGR) order.
"""

import logging
from typing import Any, List, Optional, Tuple

log = logging.getLogger(__name__)

# The page must cover at least this share of the photo to be cropped (smaller = probably a
# label or a box on the invoice, not the paper), and at most this share (larger = the photo is
# already just the page).
MIN_PAGE_AREA = 0.25
MAX_PAGE_AREA = 0.92
# Background brightness differences larger than this (0-255) count as a shadow.
SHADOW_RANGE = 40


def prepare(image: Any, flatten_page: bool = True, remove_shadows: bool = True) -> Tuple[Any, List[str]]:
    """Returns (image, list of what was done)."""
    done = []
    try:
        if flatten_page:
            flat = _flatten(image)
            if flat is not None:
                image = flat
                done.append("page flattened")
        if remove_shadows:
            even = _remove_shadows(image)
            if even is not None:
                image = even
                done.append("shadows removed")
    except Exception as error:  # noqa: BLE001 - clean-up must never stop a scan
        log.warning("Photo clean-up skipped: %s", error)
    return image, done


# ---------------------------------------------------------------- page corners

def find_page(image: Any) -> Optional[Any]:
    """The four corners of the paper (float32 array, TL TR BR BL), or None."""
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = 1000.0 / max(height, width)
    small = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else image
    scale = min(scale, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    area = float(gray.shape[0] * gray.shape[1])

    masks = []
    # 1. paper edges (not fooled by a shadow on the paper)
    edges = cv2.Canny(gray, 40, 120)
    masks.append(cv2.dilate(edges, np.ones((5, 5), np.uint8)))
    # 2. paper is brighter than what is around it
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks.append(cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)))

    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            hull = cv2.convexHull(contour)
            share = cv2.contourArea(hull) / area
            if share < MIN_PAGE_AREA:
                break
            if share > MAX_PAGE_AREA:
                continue
            corners = _four_corners(hull)
            if corners is not None and _edges_are_paper_edges(gray, corners):
                return corners / scale
    return None


def _edges_are_paper_edges(gray: Any, corners: Any) -> bool:
    """Every side of the page must be a real edge: paper clearly brighter just inside than the
    background just outside. A side on the photo border is accepted. This rejects a "page" that
    is really the bright half of a page with a shadow on it."""
    import numpy as np

    height, width = gray.shape[:2]
    centre = corners.mean(axis=0)
    margin = 4.0
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        on_border = (
            max(a[0], b[0]) <= margin or min(a[0], b[0]) >= width - 1 - margin
            or max(a[1], b[1]) <= margin or min(a[1], b[1]) >= height - 1 - margin
        )  # the whole side runs along one edge of the photo
        if on_border:
            continue
        direction = (b - a) / (np.linalg.norm(b - a) + 1e-6)
        normal = np.array([-direction[1], direction[0]])
        if np.dot(centre - (a + b) / 2, normal) < 0:
            normal = -normal  # point inwards
        differences = []
        for t in np.linspace(0.1, 0.9, 25):
            point = a + (b - a) * t
            inside, outside = point + normal * 8, point - normal * 8
            if not (0 <= outside[0] < width and 0 <= outside[1] < height):
                continue
            differences.append(float(gray[int(inside[1]), int(inside[0])]) - float(gray[int(outside[1]), int(outside[0])]))
        if len(differences) < 10 or np.median(differences) < 25:
            return False
    return True


def _four_corners(hull: Any) -> Optional[Any]:
    import cv2
    import numpy as np

    perimeter = cv2.arcLength(hull, True)
    for factor in (0.02, 0.03, 0.04, 0.05):
        approx = cv2.approxPolyDP(hull, factor * perimeter, True)
        if len(approx) == 4:
            points = approx.reshape(4, 2).astype("float32")
            ordered = _order(points)
            # reject strongly distorted shapes (two corners on the same side, etc.)
            if cv2.isContourConvex(ordered.astype("int32")) and _min_angle(ordered) > 45:
                return ordered
    return None


def _order(points: Any) -> Any:
    import numpy as np

    s = points.sum(axis=1)
    d = np.diff(points, axis=1).ravel()
    return np.array([points[np.argmin(s)], points[np.argmin(d)], points[np.argmax(s)], points[np.argmax(d)]],
                    dtype="float32")


def _min_angle(corners: Any) -> float:
    import numpy as np

    angles = []
    for i in range(4):
        a, b, c = corners[i - 1], corners[i], corners[(i + 1) % 4]
        v1, v2 = a - b, c - b
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6))
        angles.append(np.degrees(np.arccos(max(-1.0, min(1.0, cos)))))
    return min(angles)


def _flatten(image: Any) -> Optional[Any]:
    import cv2
    import numpy as np

    corners = find_page(image)
    if corners is None:
        return None
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if width < 200 or height < 200:
        return None
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(corners.astype("float32"), target)
    return cv2.warpPerspective(image, matrix, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


# ---------------------------------------------------------------- shadows

def _background(plane: Any) -> Any:
    """Brightness of the paper without the text, at full size."""
    import cv2
    import numpy as np

    height, width = plane.shape[:2]
    scale = 600.0 / max(height, width)
    small = cv2.resize(plane, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    small = cv2.dilate(small, np.ones((7, 7), np.uint8))   # remove dark text
    small = cv2.medianBlur(small, 21)
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)


def has_shadow(image: Any) -> bool:
    import cv2
    import numpy as np

    background = _background(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    low, high = np.percentile(background, [2, 98])
    return float(high - low) > SHADOW_RANGE


def _remove_shadows(image: Any) -> Optional[Any]:
    import cv2
    import numpy as np

    if not has_shadow(image):
        return None
    planes = []
    for plane in cv2.split(image):
        background = _background(plane).astype("float32")
        even = plane.astype("float32") / np.maximum(background, 1.0) * 245.0
        planes.append(np.clip(even, 0, 255).astype("uint8"))
    return cv2.merge(planes)
