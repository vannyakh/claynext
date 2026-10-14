"""Vector elements, blur masks, and callouts: outlines drive the preview painter, shelf cards, and subtitle burn-in."""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from jela.core.text_style import REF_H, anim_frame
from jela.utils.paths import BASE_DIR

# Element categories and catalog: (key, label, category, default_size, tooltip_hint)
ELEMENTS: tuple[tuple[str, str, str, tuple[float, float], str], ...] = (
    # Blur & Masks
    ("blur_rect", "Blur Box", "blur", (0.35, 0.25), "Rectangular blur zone for censoring or focus"),
    ("blur_circle", "Blur Oval", "blur", (0.3, 0.3), "Oval blur mask for faces, logos or details"),
    ("frosted_glass", "Frosted Glass", "blur", (0.45, 0.28), "Aesthetic blurred glass card with specular edge"),
    ("mosaic", "Mosaic Censor", "blur", (0.35, 0.25), "Pixelated censor plate for privacy"),
    ("vignette_blur", "Soft Vignette", "blur", (0.55, 0.38), "Soft blurred vignette card"),

    # Basic Shapes
    ("rect", "Rectangle", "shapes", (0.3, 0.3), "Standard rectangle"),
    ("rounded", "Rounded Box", "shapes", (0.3, 0.3), "Smooth rounded rectangle"),
    ("pill", "Pill Card", "shapes", (0.42, 0.2), "Pill capsule shape"),
    ("circle", "Circle", "shapes", (0.3, 0.3), "Perfect circle / oval"),
    ("ring", "Ring Donut", "shapes", (0.3, 0.3), "Hollow ring / circle outline"),
    ("triangle", "Triangle", "shapes", (0.3, 0.3), "Equilateral triangle"),
    ("diamond", "Diamond", "shapes", (0.3, 0.3), "Diamond rhombus"),
    ("star", "Star", "shapes", (0.32, 0.32), "Five-pointed star"),
    ("heart", "Heart", "shapes", (0.3, 0.3), "Heart shape"),
    ("hexagon", "Hexagon", "shapes", (0.3, 0.3), "Regular hexagon"),

    # Arrows & Lines
    ("arrow", "Arrow Right", "arrows", (0.4, 0.22), "Pointer arrow pointing right"),
    ("arrow_left", "Arrow Left", "arrows", (0.4, 0.22), "Pointer arrow pointing left"),
    ("double_arrow", "Double Arrow", "arrows", (0.44, 0.22), "Two-way horizontal arrow"),
    ("chevron", "Chevron", "arrows", (0.3, 0.3), "Modern chevron pointer"),
    ("line", "Solid Line", "arrows", (0.6, 0.02), "Horizontal divider line"),
    ("dashed_line", "Dashed Line", "arrows", (0.6, 0.02), "Dashed horizontal accent"),

    # Callouts & Badges
    ("bubble", "Speech Bubble", "callouts", (0.42, 0.3), "Comic dialogue speech bubble"),
    ("thought", "Thought Bubble", "callouts", (0.44, 0.32), "Dreamy thought cloud callout"),
    ("badge", "Badge Ribbon", "callouts", (0.36, 0.36), "Award / label seal badge"),
    ("tag", "Tag Plate", "callouts", (0.42, 0.25), "Price / label tag cutout"),

    # Icons & Symbols
    ("check", "Check Mark", "icons", (0.3, 0.3), "Check verification mark"),
    ("cross", "Cross Mark", "icons", (0.3, 0.3), "Error / cancel cross"),
    ("warning", "Warning Triangle", "icons", (0.32, 0.32), "Warning sign with exclamation"),
    ("info", "Info Circle", "icons", (0.3, 0.3), "Information notice badge"),
)

BLUR_SHAPES = frozenset({"blur_rect", "blur_circle", "frosted_glass", "mosaic", "vignette_blur"})

# Backwards-compatible aliases for existing imports
SHAPES: tuple[tuple[str, str], ...] = tuple((k, l) for k, l, *rest in ELEMENTS)
SHAPE_LABELS: dict[str, str] = {k: l for k, l, *rest in ELEMENTS}
SHAPE_SIZE: dict[str, tuple[float, float]] = {k: s for k, l, c, s, *rest in ELEMENTS}


def shape_size(key: str) -> tuple[float, float]:
    """Default (w, h) in canvas heights."""
    return SHAPE_SIZE.get(key, (0.3, 0.3))


def _polygon(points) -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    path.closeSubpath()
    return path


def _raw(key: str, aspect: float) -> QPainterPath:
    w, h = aspect, 1.0
    path = QPainterPath()

    # Blur & Glass
    if key in ("blur_rect", "mosaic"):
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), 0.08 * min(w, h), 0.08 * min(w, h))
    elif key in ("blur_circle", "vignette_blur", "circle"):
        path.addEllipse(QRectF(-w / 2, -h / 2, w, h))
    elif key == "frosted_glass":
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), 0.16 * min(w, h), 0.16 * min(w, h))

    # Basic Shapes
    elif key == "rounded":
        r = 0.2 * min(w, h)
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    elif key == "pill":
        r = min(w, h) / 2
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    elif key == "ring":
        outer = QPainterPath()
        outer.addEllipse(QRectF(-w / 2, -h / 2, w, h))
        inner = QPainterPath()
        inner.addEllipse(QRectF(-w * 0.32, -h * 0.32, w * 0.64, h * 0.64))
        path = outer.subtracted(inner)
    elif key == "triangle":
        path = _polygon([(0, -0.5), (0.5, 0.5), (-0.5, 0.5)])
    elif key == "diamond":
        path = _polygon([(0, -0.5), (0.5, 0), (0, 0.5), (-0.5, 0)])
    elif key == "star":
        pts = []
        for i in range(10):
            r = 0.5 if i % 2 == 0 else 0.22
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((r * math.cos(a), r * math.sin(a)))
        path = _polygon(pts)
    elif key == "heart":
        path.moveTo(0, 0.35)
        path.cubicTo(-0.55, -0.05, -0.3, -0.55, 0, -0.22)
        path.cubicTo(0.3, -0.55, 0.55, -0.05, 0, 0.35)
        path.closeSubpath()
    elif key == "hexagon":
        path = _polygon([(0.5 * math.cos(math.pi / 3 * i), 0.5 * math.sin(math.pi / 3 * i)) for i in range(6)])

    # Arrows & Lines
    elif key == "arrow":
        path = _polygon([(-0.5, -0.18), (0.1, -0.18), (0.1, -0.5), (0.5, 0), (0.1, 0.5), (0.1, 0.18), (-0.5, 0.18)])
    elif key == "arrow_left":
        path = _polygon([(0.5, -0.18), (-0.1, -0.18), (-0.1, -0.5), (-0.5, 0), (-0.1, 0.5), (-0.1, 0.18), (0.5, 0.18)])
    elif key == "double_arrow":
        path = _polygon([(-0.5, 0), (-0.2, -0.4), (-0.2, -0.16), (0.2, -0.16), (0.2, -0.4),
                         (0.5, 0), (0.2, 0.4), (0.2, 0.16), (-0.2, 0.16), (-0.2, 0.4)])
    elif key == "chevron":
        path = _polygon([(-0.35, -0.5), (0.05, 0), (-0.35, 0.5), (-0.05, 0.5), (0.35, 0), (-0.05, -0.5)])
    elif key in ("line", "dashed_line"):
        path.addRect(QRectF(-w / 2, -h / 2, w, h))

    # Callouts & Badges
    elif key == "bubble":
        body = QPainterPath()
        body.addRoundedRect(QRectF(-w / 2, -h / 2, w, h * 0.78), 0.18 * h, 0.18 * h)
        tail = _polygon([(-w * 0.2, h * 0.2), (-w * 0.32, h / 2), (-w * 0.02, h * 0.2)])
        path = body.united(tail).simplified()
    elif key == "thought":
        body = QPainterPath()
        body.addRoundedRect(QRectF(-w * 0.44, -h * 0.44, w * 0.88, h * 0.68), 0.24 * h, 0.24 * h)
        t1 = QPainterPath()
        t1.addEllipse(QRectF(-w * 0.30, h * 0.26, w * 0.14, h * 0.14))
        t2 = QPainterPath()
        t2.addEllipse(QRectF(-w * 0.42, h * 0.38, w * 0.09, h * 0.09))
        path = body.united(t1).united(t2).simplified()
    elif key == "badge":
        pts = []
        for i in range(16):
            r = 0.5 if i % 2 == 0 else 0.42
            a = i * math.pi / 8
            pts.append((r * math.cos(a) * w, r * math.sin(a) * h))
        path = _polygon(pts)
    elif key == "tag":
        tag_poly = _polygon([(-w * 0.5, 0), (-w * 0.28, -h * 0.5), (w * 0.5, -h * 0.5),
                             (w * 0.5, h * 0.5), (-w * 0.28, h * 0.5)])
        hole = QPainterPath()
        hole.addEllipse(QRectF(-w * 0.32, -h * 0.14, w * 0.12, h * 0.28))
        path = tag_poly.subtracted(hole)

    # Icons & Symbols
    elif key == "check":
        path = _polygon([(-0.4, 0.0), (-0.15, 0.38), (0.45, -0.36), (0.32, -0.48), (-0.15, 0.15), (-0.28, -0.05)])
    elif key == "cross":
        t = 0.15
        path = _polygon([(-0.5, -0.5 + t), (-0.5 + t, -0.5), (0, -t), (0.5 - t, -0.5), (0.5, -0.5 + t),
                         (t, 0), (0.5, 0.5 - t), (0.5 - t, 0.5), (0, t), (-0.5 + t, 0.5), (-0.5, 0.5 - t), (-t, 0)])
    elif key == "warning":
        tri = _polygon([(0, -0.5), (0.5, 0.45), (-0.5, 0.45)])
        mark = QPainterPath()
        mark.addRoundedRect(QRectF(-0.04, -0.22, 0.08, 0.36), 0.03, 0.03)
        mark.addEllipse(QRectF(-0.05, 0.22, 0.10, 0.10))
        path = tri.subtracted(mark)
    elif key == "info":
        circle = QPainterPath()
        circle.addEllipse(QRectF(-w / 2, -h / 2, w, h))
        dot = QPainterPath()
        dot.addEllipse(QRectF(-0.06, -0.32, 0.12, 0.12))
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(-0.05, -0.12, 0.10, 0.40), 0.04, 0.04)
        path = circle.subtracted(dot).subtracted(bar)

    else:
        path.addRect(QRectF(-w / 2, -h / 2, w, h))

    return path


@lru_cache(maxsize=256)
def shape_path(key: str, aspect: float) -> QPainterPath:
    """Outline whose control box is exactly (-aspect/2, -1/2, aspect, 1)."""
    path = _raw(key, aspect)
    box = path.controlPointRect()
    if box.width() <= 0 or box.height() <= 0:
        return path
    t = QTransform()
    t.scale(aspect / box.width(), 1.0 / box.height())
    t.translate(-box.center().x(), -box.center().y())
    return t.map(path)


def shape_px(style: dict, item_w: float, item_h: float, canvas_h: float) -> tuple[float, float]:
    k = style["scale"] / 100.0 * canvas_h
    return max(1.0, item_w * k), max(1.0, item_h * k)


def fast_blur_image(img: QImage, radius: int = 24) -> QImage:
    """Downscale / upscale multi-pass blur in sub-millisecond C++ Qt."""
    if img.isNull() or img.width() <= 2 or img.height() <= 2:
        return img
    r = max(2, min(100, radius))
    div = max(2, min(32, int(r * 0.35 + 2)))
    smooth = Qt.TransformationMode.SmoothTransformation
    w, h = img.width(), img.height()
    small = img.scaled(max(2, w // div), max(2, h // div), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    mid = small.scaled(max(2, w // 2), max(2, h // 2), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    return mid.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)


def mosaic_image(img: QImage, cell_size: int = 14) -> QImage:
    """Authentic pixelated censor plate."""
    if img.isNull() or img.width() <= 2 or img.height() <= 2:
        return img
    cs = max(4, min(48, cell_size))
    w, h = img.width(), img.height()
    fast = Qt.TransformationMode.FastTransformation
    small = img.scaled(max(2, w // cs), max(2, h // cs), Qt.AspectRatioMode.IgnoreAspectRatio, fast)
    return small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, fast)


def paint_shape(
    p: QPainter,
    style: dict,
    key: str,
    size: tuple[float, float],
    center: QPointF,
    canvas_h: float,
    rotation: float = 0.0,
    frame: dict | None = None,
    bg_image: QImage | None = None,
    canvas_rect: QRectF | None = None,
):
    frame = frame or anim_frame(style, 0, 0)
    if frame["alpha"] <= 0.001:
        return
    w, h = size
    aspect = round(w / max(1e-3, h), 3)
    path = QTransform.fromScale(h, h).map(shape_path(key, aspect))

    cx = center.x() + frame["dx"] * canvas_h
    cy = center.y() + frame["dy"] * canvas_h
    scale = frame["scale"]
    rot = rotation + frame["rot"]

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.translate(cx, cy)
    p.rotate(rot)
    p.scale(scale, scale)
    p.setOpacity(p.opacity() * (style.get("opacity", 100) / 100.0) * frame["alpha"])

    k = canvas_h / REF_H
    is_blur_kind = (key in BLUR_SHAPES) or bool(style.get("blur_on", False))

    if is_blur_kind:
        # Live video blur / mosaic / frosted glass
        if bg_image is not None and not bg_image.isNull() and canvas_rect is not None and canvas_rect.width() > 0:
            item_box_w = w * scale
            item_box_h = h * scale
            rel_cx = (cx - canvas_rect.left()) / canvas_rect.width()
            rel_cy = (cy - canvas_rect.top()) / canvas_rect.height()
            rel_w = item_box_w / canvas_rect.width()
            rel_h = item_box_h / canvas_rect.height()

            img_w, img_h = bg_image.width(), bg_image.height()
            crop_cx = rel_cx * img_w
            crop_cy = rel_cy * img_h
            crop_w = max(4, int(round(rel_w * img_w)))
            crop_h = max(4, int(round(rel_h * img_h)))
            crop_x = int(round(crop_cx - crop_w / 2))
            crop_y = int(round(crop_cy - crop_h / 2))

            src_x = max(0, min(img_w - 4, crop_x))
            src_y = max(0, min(img_h - 4, crop_y))
            src_w = max(4, min(img_w - src_x, crop_w))
            src_h = max(4, min(img_h - src_y, crop_h))

            sub_img = bg_image.copy(src_x, src_y, src_w, src_h)
            radius = int(style.get("blur_radius", 24))

            if key == "mosaic":
                processed = mosaic_image(sub_img, cell_size=max(6, int(radius * 0.45)))
            else:
                processed = fast_blur_image(sub_img, radius=radius)

            p.save()
            p.setClipPath(path)
            target_rect = QRectF(-w / 2, -h / 2, w, h)
            p.drawImage(target_rect, processed)

            if key == "frosted_glass":
                grad = QLinearGradient(-w / 2, -h / 2, w / 2, h / 2)
                grad.setColorAt(0.0, QColor(255, 255, 255, 45))
                grad.setColorAt(0.5, QColor(255, 255, 255, 18))
                grad.setColorAt(1.0, QColor(255, 255, 255, 32))
                p.fillPath(path, grad)
            elif key == "vignette_blur":
                rad = QRadialGradient(0, 0, max(w, h) / 2)
                rad.setColorAt(0.0, QColor(0, 0, 0, 0))
                rad.setColorAt(0.7, QColor(0, 0, 0, 40))
                rad.setColorAt(1.0, QColor(0, 0, 0, 110))
                p.fillPath(path, rad)
            p.restore()
        else:
            grad = QLinearGradient(-w / 2, -h / 2, w / 2, h / 2)
            grad.setColorAt(0.0, QColor(255, 255, 255, 55))
            grad.setColorAt(0.5, QColor(255, 255, 255, 22))
            grad.setColorAt(1.0, QColor(255, 255, 255, 38))
            p.fillPath(path, grad)

        if key == "frosted_glass":
            p.strokePath(path, QPen(QColor(255, 255, 255, 140), 1.5))
        elif key in ("blur_rect", "blur_circle"):
            p.strokePath(
                path,
                QPen(
                    QColor(255, 255, 255, 65),
                    1.0,
                    Qt.PenStyle.DashLine if not style.get("stroke_on") else Qt.PenStyle.SolidLine,
                ),
            )
        elif key == "mosaic":
            p.strokePath(path, QPen(QColor(0, 0, 0, 100), 1.0))

    else:
        if style.get("shadow_on"):
            d = style.get("shadow_dist", 2) * k
            shade = QColor(style.get("shadow_color", "#000000"))
            shade.setAlphaF(0.8)
            p.fillPath(path.translated(d, d), shade)

        if key == "dashed_line":
            p.setPen(
                QPen(
                    QColor(style.get("color", "#f8fafc")),
                    max(2.0, 3 * k),
                    Qt.PenStyle.DashLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            p.drawLine(QPointF(-w / 2, 0), QPointF(w / 2, 0))
        elif key == "line":
            p.setPen(
                QPen(
                    QColor(style.get("color", "#f8fafc")),
                    max(2.0, 3 * k),
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            p.drawLine(QPointF(-w / 2, 0), QPointF(w / 2, 0))
        else:
            p.fillPath(path, QColor(style.get("color", "#f8fafc")))

    if style.get("stroke_on"):
        sw = max(1.0, 2 * style.get("stroke_width", 3) * k)
        p.strokePath(
            path,
            QPen(
                QColor(style.get("stroke_color", "#000000")),
                sw,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ),
        )

    p.restore()


def shape_drawing(key: str, aspect: float) -> list[list]:
    """The outline as ["m"|"l"|"b", x, y, ...] commands in canvas heights, centred on (0, 0)."""
    path = shape_path(key, round(aspect, 3))
    out: list[list] = []
    i = 0
    n = path.elementCount()
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append(["m", e.x, e.y])
        elif e.isLineTo():
            out.append(["l", e.x, e.y])
        elif e.isCurveTo() and i + 2 < n:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(["b", e.x, e.y, c2.x, c2.y, end.x, end.y])
            i += 2
        i += 1
    return out


@lru_cache(maxsize=1)
def sample_cinematic_image() -> np.ndarray:
    """A realistic cinematic movie still used for backdrop of blur previews and fx tiles."""
    w, h = 212, 124
    img_path = BASE_DIR / "assets" / "images" / "fx_preview_base.jpg"
    if img_path.is_file():
        try:
            from PIL import Image

            im = Image.open(img_path).convert("RGB")
            scale = max(w / im.width, h / im.height)
            nw, nh = int(round(im.width * scale)), int(round(im.height * scale))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
            left = max(0, (nw - w) // 2)
            top = max(0, (nh - h) // 2)
            im = im.crop((left, top, left + w, top + h))
            return np.array(im, dtype=np.uint8)
        except Exception:
            pass

    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    sky = (1 - y) * np.array([86, 140, 214], np.float32) + y * np.array([250, 178, 120], np.float32)
    img = np.broadcast_to(sky, (h, w, 3)).copy()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sun = (xx - w * 0.68) ** 2 + (yy - h * 0.42) ** 2 < (h * 0.16) ** 2
    img[sun] = (255, 236, 170)
    hill = yy > h * (0.66 + 0.08 * np.sin(xx / w * 6.0))
    img[hill] = np.array([46, 110, 92], np.float32) * (1.1 - 0.4 * (yy[hill] / h))[:, None]
    person = (np.abs(xx - w * 0.3) < w * 0.05) & (yy > h * 0.45) & (yy < h * 0.8)
    img[person] = (220, 72, 84)
    return np.clip(img, 0, 255).astype(np.uint8)


@lru_cache(maxsize=128)
def element_tile_pixmap(key: str) -> QPixmap:
    """Rich Cyber Dark studio element card with live blur demonstration."""
    w, h = 212, 124  # 106x62 @ 2x DPR
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    r = 12.0
    card_path = QPainterPath()
    card_path.addRoundedRect(0, 0, w, h, r, r)

    if key in BLUR_SHAPES:
        base = sample_cinematic_image().copy()
        bh, bw = base.shape[:2]
        src_img = QImage(base.data, bw, bh, 3 * bw, QImage.Format.Format_RGB888)
        scaled_bg = src_img.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        crop_bg = scaled_bg.copy((scaled_bg.width() - w) // 2, (scaled_bg.height() - h) // 2, w, h)

        p.save()
        p.setClipPath(card_path)
        p.drawImage(0, 0, crop_bg)

        # Subtle dark veil over background
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, 70))

        ew, eh = shape_size(key)
        fit = 0.64 * min(w, h) / max(ew, eh)
        elem_w, elem_h = ew * fit, eh * fit
        elem_path = QTransform.fromScale(elem_h, elem_h).map(shape_path(key, round(ew / eh, 3)))
        elem_path.translate(w / 2, h / 2)

        crop_rect = QRectF((w - elem_w) / 2, (h - elem_h) / 2, elem_w, elem_h)
        sub = crop_bg.copy(
            int(crop_rect.left()), int(crop_rect.top()), int(crop_rect.width()), int(crop_rect.height())
        )

        if key == "mosaic":
            proc = mosaic_image(sub, 9)
        else:
            proc = fast_blur_image(sub, 28)

        p.save()
        p.setClipPath(elem_path)
        p.drawImage(crop_rect.topLeft(), proc)
        if key == "frosted_glass":
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 60))
            grad.setColorAt(1.0, QColor(255, 255, 255, 25))
            p.fillPath(elem_path, grad)
        p.restore()

        if key == "frosted_glass":
            p.strokePath(elem_path, QPen(QColor(255, 255, 255, 180), 2.0))
        elif key == "mosaic":
            p.strokePath(elem_path, QPen(QColor(0, 0, 0, 160), 1.5))
        else:
            p.strokePath(elem_path, QPen(QColor(255, 255, 255, 130), 1.6, Qt.PenStyle.DashLine))

        badge_rect = QRectF(w - 56, 8, 48, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(99, 102, 241, 215))
        p.drawRoundedRect(badge_rect, 4, 4)
        p.setPen(QColor("#ffffff"))
        f = p.font()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        badge_txt = "PIXEL" if key == "mosaic" else ("GLASS" if key == "frosted_glass" else "BLUR")
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_txt)

        p.restore()

    else:
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(20, 29, 44))
        bg_grad.setColorAt(1.0, QColor(11, 16, 25))
        p.fillPath(card_path, bg_grad)

        glow = QRadialGradient(w / 2, h / 2, w * 0.45)
        glow.setColorAt(0.0, QColor(99, 102, 241, 35))
        glow.setColorAt(1.0, QColor(99, 102, 241, 0))
        p.fillPath(card_path, glow)

        ew, eh = shape_size(key)
        fit = 0.52 * min(w, h) / max(ew, eh)
        path = QTransform.fromScale(eh * fit, eh * fit).map(shape_path(key, round(ew / eh, 3)))
        path.translate(w / 2, h / 2)

        # Drop shadow
        p.fillPath(path.translated(2, 3), QColor(0, 0, 0, 110))

        if key == "dashed_line":
            p.setPen(QPen(QColor("#e2e8f0"), 4.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(w * 0.18, h / 2), QPointF(w * 0.82, h / 2))
        elif key == "line":
            p.setPen(QPen(QColor("#e2e8f0"), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(w * 0.18, h / 2), QPointF(w * 0.82, h / 2))
        else:
            p.fillPath(path, QColor("#e2e8f0"))

    # Outer border of card
    p.setPen(QPen(QColor(255, 255, 255, 22), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(0.75, 0.75, w - 1.5, h - 1.5, r, r)
    p.end()

    pix.setDevicePixelRatio(2.0)
    return pix


def element_tile_icon(key: str) -> QIcon:
    return QIcon(element_tile_pixmap(key))


def shape_icon(key: str, color: str = "#e7ecf3", side: int = 40) -> QIcon:
    """Inspector tool button icon."""
    pix = QPixmap(side * 2, side * 2)
    pix.setDevicePixelRatio(2.0)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    w, h = shape_size(key)
    fit = 0.72 * side / max(w, h)
    path = QTransform.fromScale(h * fit, h * fit).map(shape_path(key, round(w / h, 3)))
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(side / 2, side / 2)
    if key in BLUR_SHAPES:
        p.fillPath(path, QColor(99, 102, 241, 140))
        p.strokePath(path, QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
    elif key == "dashed_line":
        p.setPen(QPen(QColor(color), 2.5, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-side * 0.38, 0), QPointF(side * 0.38, 0))
    elif key == "line":
        p.setPen(QPen(QColor(color), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-side * 0.38, 0), QPointF(side * 0.38, 0))
    else:
        p.fillPath(path, QColor(color))
    p.end()
    return QIcon(pix)
