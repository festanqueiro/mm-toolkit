# Changelog

All notable changes to MM Toolkit are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the
policy in `CLAUDE.md` (patch by default, minor/major only when requested).

## [Unreleased]

### Added
- Reusable, drag-reorderable visual effects cascade for Video Creator
  (Overlay, Bass-reactive Blur, Rotate, VHS, Glitch), plus a separate Layers
  section for Background fill/image and Overlay image.
- Tray notification + History badge on job completion, replacing the old
  completion popups; clicking a notification opens History with that job
  selected.

### Changed
- Renamed "Video Generator" to "Video Creator" throughout the app and
  codebase (`VideoGeneratorTab` → `VideoCreatorTab`,
  `video_generator.py` → `video_creator.py`). Saved History entries keep
  their existing `"promo"` tool key, so old history still loads.
- Video Creator's Audio clips table now matches Media Cutter's table styling
  (alternating rows, no grid, hidden vertical header, styled borders).
- Halved the Rotate effect's displayed speed to match its actual on-screen
  spin rate.
- Overlay is scoped to still images only (dropped the video-overlay path
  for simplicity).

### Fixed
- Collapsible sections holding an expanding widget (e.g. a table) no longer
  keep claiming leftover vertical space while collapsed — they now shrink
  to header height like every other section.
- Rotate no longer leaves a visible dark seam at the rotated edge.
- File/folder pickers use the OS-native dialog again instead of Qt's.
- Image/video/overlay/background pickers now open in the current audio
  file's folder by default.

## [1.0.1] - 2026-08-18

### Added
- Rendered-file preview player in the History tab.
- Dev-build indicator in the About tab.

### Changed
- Adopted [Conventional Commits](https://www.conventionalcommits.org/) for
  commit messages; documented the release versioning policy.
- General UI readability improvements.

## [1.0.0] - 2026-08-17

Initial release: cross-platform record-label media tools — Video Generator
(promo video rendering from audio + artwork/video), Media Cutter, Media
Converter, History, and Settings tabs, packaged for macOS and Windows.
