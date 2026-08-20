# TODO

Future feature ideas that are out of scope for the current work, tracked here so they aren't lost.

## Video Creator rename (Prio 1 - urgent) — done

Renamed "Video Generator" everywhere: tab label, page title/subtitle,
tooltips, and internals (`VideoGeneratorTab` → `VideoCreatorTab`,
`video_generator.py` → `video_creator.py`, `self.video_generator` →
`self.video_creator` in `main_window.py`, doc references in `effects.py`/
`effects_panel.py`, README/CLAUDE.md). Saved History entries still key on
`"tool": "promo"`, kept as-is so old history entries still load.

## Audio timestamps section collapsed height (Prio 1 - urgent) — done

Fixed: `Accordion` (`helpers.py`) now has a `bind_stretch(group, layout)`
method that sets the group's stretch factor to 1 only while its toggle is
checked, and 0 while collapsed, instead of a permanent stretch factor. Wired
up for the "Audio timestamps" section in `video_creator.py`. Verified by
constructing `MainWindow` and checking the layout's stretch factor toggles
0 ↔ 1 as the section expands/collapses.

## Layers (Prio 1)

- **Background enable/disable.** Add a checkbox, off by default. Off means
  no background layer is rendered at all — no color/image fill; letterboxed
  areas and the corners revealed by Rotate stay transparent/black instead of
  showing a fill color. When on, the existing Fill (Solid color/Image)
  combo and controls become active as they are today.
- **Color swatch placement.** Move the color-preview swatch onto the same
  row as the Fill combo box (beside it), instead of its own "Color" row
  below.
- **Overlay image.** TODO said this "is not working," but `c1e1309` (today,
  same branch) already fixed overlay to be image-only and was verified with
  a render. Re-test on this branch before doing any further work here — if
  it's still broken, capture the actual repro (which image, which visual
  input, what's on screen) rather than assuming the old bug report is still
  accurate.

## Visual Effects (Prio 1)

- **VHS moving bars.** Add a scrolling brightness/tracking-error band —
  a soft horizontal band of brightness distortion that continuously scrolls
  from bottom to top of the frame over time — layered on top of the
  existing scanline/chromatic-aberration/noise look in `apply_vhs`
  (`mm_toolkit/effects.py`). Driven by `time`, same as the rest of the VHS
  effect, so it's deterministic per-frame like the other effects.
- **Layers vs. cascade ordering control.** Add a select box with two
  options: apply the VHS/Glitch/B&W/Negative/Bass-Blur/Rotate cascade
  *before* the Layers (Background fill + Overlay image) are composited, or
  *after*. This is a single global toggle over the whole cascade relative to
  Layers — separate from (and in addition to) the existing per-effect
  drag-to-reorder list, which keeps controlling relative order *within* the
  cascade itself.
- **New effects.** Add "Black & White" and "Negative" to the effect stack,
  following the existing pattern (`_EFFECT_DEFS` in `effects_panel.py`,
  a settings dataclass + branch in `apply_effect_chain` in `effects.py`).
  Black & White: desaturate to greyscale. Negative: invert RGB channels.
  Both are simple boolean effects (no dry/wet amount needed, similar to
  Bass-reactive Blur/Rotate) unless a dry/wet blend is wanted later.
- **Drag-hint text color.** "Drag rows to change the order effects are
  applied in." currently uses `color: palette(mid)` and reads as
  unreadable near-black in practice. Replace with an explicit light grey
  that's legible in both light and dark mode (check against both themes,
  not just the current one).

## Update Video Creator's Audio clips table UI (Prio 1 - urgent) — done

Restyled `self.promo_tracks` in `video_creator.py` to match `self.table` in
`clips_tab.py`: alternating row colors, no grid lines, hidden vertical
header, the same rounded-border/styled-header stylesheet, and `SelectRows` /
`SingleSelection` selection behavior. Column layout unchanged (Audio /
Start / Duration / preview button) — only the visual chrome was unified,
not the columns.

## Rolling Text Overlay (Prio 3)

Possibility to add a per-audio text overlay effect where the text scrolls
right to left across the frame, like a news-ticker panel on TV news shows.

## History tab as a Task Manager (Prio 3)

The History tab should also work as a task manager: show the progress of each
dispatched job (Video Creator, Media Cutter, Media Converter), not just
finished ones. Dispatched jobs would stack as pending/in-progress entries
above the completed history list, each showing live status (queued,
rendering N%, done/failed), so starting several generations in a row is
visible at a glance instead of only being visible on whichever tab launched
them.
