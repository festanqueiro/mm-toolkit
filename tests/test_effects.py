import numpy as np

from mm_toolkit.effects import (
    BackgroundSettings,
    EffectSettings,
    GlitchSettings,
    RotateSettings,
    VhsSettings,
    apply_effect_chain,
    apply_glitch,
    apply_radial_blur,
    apply_rotate,
    apply_vhs,
    build_background_frame,
)


def _frame(width: int = 40, height: int = 30) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = (200, 120, 40)
    frame[height // 2 :, width // 2 :] = (10, 220, 90)
    return frame


def test_build_background_frame_fills_solid_color() -> None:
    background = build_background_frame((16, 10), BackgroundSettings(color=(1, 2, 3)))
    assert background.shape == (10, 16, 3)
    assert (background == (1, 2, 3)).all()


def test_build_background_frame_falls_back_to_color_for_missing_image(tmp_path) -> None:
    missing = tmp_path / "missing.png"
    background = build_background_frame((8, 8), BackgroundSettings(mode="image", image_path=str(missing), color=(9, 9, 9)))
    assert (background == (9, 9, 9)).all()


def test_radial_blur_is_noop_below_strength_floor() -> None:
    frame = _frame()
    assert np.array_equal(apply_radial_blur(frame, 0.0), frame)


def test_radial_blur_changes_frame_above_strength_floor() -> None:
    frame = _frame()
    blurred = apply_radial_blur(frame, 1.0)
    assert blurred.shape == frame.shape
    assert not np.array_equal(blurred, frame)


def test_rotate_reveals_background_at_corners() -> None:
    frame = _frame(40, 40)
    background = np.zeros_like(frame)
    background[:, :] = (5, 5, 5)
    rotated = apply_rotate(frame, 45.0, background)
    assert rotated.shape == frame.shape
    assert tuple(rotated[0, 0]) == (5, 5, 5)


def test_rotate_noop_at_zero_degrees() -> None:
    frame = _frame()
    background = np.zeros_like(frame)
    assert np.array_equal(apply_rotate(frame, 0.0, background), frame)


def test_vhs_dry_is_noop() -> None:
    frame = _frame()
    assert np.array_equal(apply_vhs(frame, 0.0, 1.0), frame)


def test_vhs_wet_changes_frame() -> None:
    frame = _frame()
    wet = apply_vhs(frame, 1.0, 1.0)
    assert wet.shape == frame.shape
    assert not np.array_equal(wet, frame)


def test_glitch_dry_is_noop() -> None:
    frame = _frame()
    assert np.array_equal(apply_glitch(frame, 0.0, 1.0), frame)


def test_glitch_wet_changes_frame() -> None:
    frame = _frame()
    glitched = apply_glitch(frame, 1.0, 1.0)
    assert glitched.shape == frame.shape
    assert not np.array_equal(glitched, frame)


def test_effect_chain_applies_enabled_effects_in_order() -> None:
    frame = _frame(40, 40)
    background = np.zeros_like(frame)
    background[:, :] = (5, 5, 5)
    settings = EffectSettings(
        background=BackgroundSettings(color=(5, 5, 5)),
        rotate=RotateSettings(enabled=True, rpm=60.0),
        vhs=VhsSettings(enabled=True, amount=0.5),
        glitch=GlitchSettings(enabled=True, amount=0.5),
    )
    result = apply_effect_chain(frame, 1.0, settings, background, bass_strength=1.0)
    assert result.shape == frame.shape


def test_effect_chain_is_noop_with_default_settings() -> None:
    frame = _frame()
    background = np.zeros_like(frame)
    assert np.array_equal(apply_effect_chain(frame, 0.0, EffectSettings(), background), frame)
