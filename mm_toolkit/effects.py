"""Reusable, platform-neutral video effects.

Effects are pure functions over full RGB uint8 frames so the same cascade can
be reused by any render pipeline (currently the Video Generator's promo
renderer in core.py), not just the tab it was first built for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

BLUR_SAMPLES = 6
MAX_ZOOM = 0.10
STRENGTH_FLOOR = 0.05


@dataclass(frozen=True)
class BackgroundSettings:
    """The layer revealed behind/around the main visual (e.g. by Rotate)."""

    mode: str = "color"  # "color" | "image"
    color: tuple[int, int, int] = (25, 25, 29)
    image_path: str | None = None


@dataclass(frozen=True)
class OverlaySettings:
    """A second image or video composited on top of the frame.

    Unlike `background` (the foundation, always applied first), overlay is a
    step in the reorderable cascade: by default it's applied before the
    other effects (so they also act on the overlaid result), but dragging it
    below them in `EffectSettings.order` composites it after instead.
    """

    enabled: bool = False
    media_path: str | None = None
    opacity: float = 1.0  # 0..1, on top of the source's own alpha channel


@dataclass(frozen=True)
class BassBlurSettings:
    """Bass-reactive zoom blur, driven by an externally supplied envelope."""

    enabled: bool = True


@dataclass(frozen=True)
class RotateSettings:
    """Continuous rotation, e.g. a spinning-vinyl look."""

    enabled: bool = False
    rpm: float = 33.3  # revolutions per minute


@dataclass(frozen=True)
class VhsSettings:
    """Chromatic aberration + scanlines + grain, blended dry/wet."""

    enabled: bool = False
    amount: float = 0.5  # 0 = dry, 1 = fully wet


@dataclass(frozen=True)
class GlitchSettings:
    """Random slice-shift + channel-split digital glitch, blended dry/wet."""

    enabled: bool = False
    amount: float = 0.5  # 0 = dry, 1 = fully wet


#: The effect keys apply_effect_chain understands, in their default cascade
#: order. `EffectSettings.order` may list them in any order/subset — this
#: tuple is only the fallback and the set of valid keys. Add a new effect by
#: adding a settings dataclass, a branch in apply_effect_chain, and a key here.
#: "overlay" defaults first so the other effects act on the overlaid result;
#: dragging it below them applies it after instead.
DEFAULT_EFFECT_ORDER: tuple[str, ...] = ("overlay", "bass_blur", "rotate", "vhs", "glitch")


@dataclass(frozen=True)
class EffectSettings:
    """A user-orderable cascade of optional visual effects.

    `order` lists effect keys (from DEFAULT_EFFECT_ORDER) in the sequence
    they should be applied; each key's own settings carry whether it's
    actually enabled. This lets a UI offer a drag-reorderable effect stack
    without the render pipeline caring about presentation.
    """

    background: BackgroundSettings = BackgroundSettings()
    order: tuple[str, ...] = DEFAULT_EFFECT_ORDER
    overlay: OverlaySettings = OverlaySettings()
    bass_blur: BassBlurSettings = BassBlurSettings()
    rotate: RotateSettings = RotateSettings()
    vhs: VhsSettings = VhsSettings()
    glitch: GlitchSettings = GlitchSettings()


def build_background_frame(size: tuple[int, int], settings: BackgroundSettings) -> np.ndarray:
    """Render the background layer once, at the given (width, height) canvas size."""
    width, height = size
    if settings.mode == "image" and settings.image_path:
        path = Path(settings.image_path)
        if path.is_file():
            with Image.open(path) as image:
                fitted = ImageOps.fit(image.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
            return np.array(fitted, dtype=np.uint8)
    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:, :] = settings.color
    return canvas


def fit_overlay_frame(rgba_frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Fit an RGBA frame into the given canvas size, centered on transparency."""
    width, height = size
    image = Image.fromarray(np.asarray(rgba_frame, dtype=np.uint8)).convert("RGBA")
    fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return np.array(canvas, dtype=np.uint8)


def load_overlay_image(path: Path, size: tuple[int, int]) -> np.ndarray:
    """Load a still image as an RGBA overlay frame fitted to `size`, alpha intact."""
    with Image.open(path) as image:
        rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    return fit_overlay_frame(rgba, size)


def apply_overlay(frame: np.ndarray, overlay_rgba: np.ndarray, opacity: float) -> np.ndarray:
    """Alpha-composite an RGBA overlay frame onto `frame`, scaled by `opacity`."""
    if opacity <= 0:
        return frame
    alpha = (overlay_rgba[..., 3:4].astype(np.float32) / 255.0) * opacity
    rgb = overlay_rgba[..., :3].astype(np.float32)
    blended = rgb * alpha + frame.astype(np.float32) * (1 - alpha)
    return blended.astype(np.uint8)


def apply_radial_blur(frame: np.ndarray, strength: float) -> np.ndarray:
    """Bass-reactive zoom blur. `strength` is 0 (untouched) to 1 (maximum)."""
    if strength <= STRENGTH_FLOOR:
        return frame
    height, width = frame.shape[:2]
    accumulator = np.zeros_like(frame, dtype=np.float32)
    for index in range(1, BLUR_SAMPLES + 1):
        zoom = 1.0 + MAX_ZOOM * strength * index / BLUR_SAMPLES
        resized = cv2.resize(
            frame,
            (int(round(width * zoom)), int(round(height * zoom))),
            interpolation=cv2.INTER_LINEAR,
        )
        y = (resized.shape[0] - height) // 2
        x = (resized.shape[1] - width) // 2
        accumulator += resized[y : y + height, x : x + width].astype(np.float32)
    return (accumulator / BLUR_SAMPLES).astype(np.uint8)


def apply_rotate(frame: np.ndarray, angle_degrees: float, background: np.ndarray) -> np.ndarray:
    """Rotate the frame around its center, revealing `background` at the corners."""
    height, width = frame.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle_degrees, 1.0)
    # BORDER_REPLICATE (not the default black-fill) so linear interpolation
    # right at the rotated edge blends real image colors, not black — a
    # black-filled border there produces a visible dark seam once alpha
    # blended against `background`, even though alpha itself anti-aliases
    # cleanly.
    rotated = cv2.warpAffine(
        frame, matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    coverage = cv2.warpAffine(
        np.full((height, width), 255, dtype=np.uint8), matrix, (width, height), flags=cv2.INTER_LINEAR
    )
    alpha = (coverage.astype(np.float32) / 255.0)[..., None]
    blended = rotated.astype(np.float32) * alpha + background.astype(np.float32) * (1 - alpha)
    return blended.astype(np.uint8)


def apply_vhs(frame: np.ndarray, amount: float, time: float) -> np.ndarray:
    """Chromatic-aberration + scanline + grain VHS look, blended dry/wet by `amount`."""
    if amount <= 0:
        return frame
    height, _width = frame.shape[:2]
    shift = max(1, round(6 * amount))
    b, g, r = cv2.split(frame)
    wet = cv2.merge([np.roll(b, -shift, axis=1), g, np.roll(r, shift, axis=1)]).astype(np.float32)
    scanlines = np.ones((height, 1), dtype=np.float32)
    scanlines[::2] = 1.0 - 0.35 * amount
    wet *= scanlines[:, None]
    noise = np.random.default_rng(int(time * 1000)).normal(0, 10 * amount, frame.shape).astype(np.float32)
    wet = np.clip(wet + noise, 0, 255).astype(np.uint8)
    return cv2.addWeighted(frame, 1 - amount, wet, amount, 0)


def apply_glitch(frame: np.ndarray, amount: float, time: float) -> np.ndarray:
    """Random horizontal slice-shift + channel-split glitch, blended dry/wet by `amount`."""
    if amount <= 0:
        return frame
    height, width = frame.shape[:2]
    rng = np.random.default_rng(int(time * 1000) + 1)
    wet = frame.copy()
    for _ in range(int(2 + 10 * amount)):
        if rng.random() > amount + 0.2:
            continue
        y0 = int(rng.integers(0, height))
        y1 = min(height, y0 + int(rng.integers(2, max(3, int(height * 0.05) + 1))))
        shift = int(rng.integers(-width // 8, width // 8 + 1))
        wet[y0:y1] = np.roll(wet[y0:y1], shift, axis=1)
    if amount > 0.3:
        shift = round(4 * amount)
        b, g, r = cv2.split(wet)
        wet = cv2.merge([b, g, np.roll(r, shift, axis=1)])
    return cv2.addWeighted(frame, 1 - amount, wet, amount, 0)


def apply_effect_chain(
    frame: np.ndarray,
    time: float,
    settings: EffectSettings,
    background: np.ndarray,
    bass_strength: float | None = None,
    overlay_frame: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the effect cascade to one frame, in the order `settings.order` lists."""
    result = frame
    for key in settings.order:
        if key == "overlay":
            if settings.overlay.enabled and overlay_frame is not None:
                result = apply_overlay(result, overlay_frame, settings.overlay.opacity)
        elif key == "bass_blur":
            if settings.bass_blur.enabled and bass_strength is not None:
                result = apply_radial_blur(result, bass_strength)
        elif key == "rotate":
            if settings.rotate.enabled:
                # /120 rather than /60: the literal RPM math read as twice
                # too fast on screen (e.g. the 33.3 RPM vinyl default spun
                # like 66 RPM), so the displayed value is halved here.
                angle = (time * settings.rotate.rpm / 120.0) * 360.0
                result = apply_rotate(result, angle, background)
        elif key == "vhs":
            if settings.vhs.enabled:
                result = apply_vhs(result, settings.vhs.amount, time)
        elif key == "glitch":
            if settings.glitch.enabled:
                result = apply_glitch(result, settings.glitch.amount, time)
    return result
