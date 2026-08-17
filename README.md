# Media Tools for Record Labels

A macOS-first desktop app for recurring record-label video workflows. The application uses a cross-platform Python/Qt codebase so the same UI can be packaged for Windows later.

The macOS bundle, Windows executable, and application windows use the rounded platform-style Media Tools icon from `assets/`.

## Promo Videos tab

- Pick one audio file or a folder and immediately verify the supported files found.
- Supports WAV, AIFF, FLAC, MP3, M4A, AAC, and OGG input through FFmpeg.
- Pick and validate PNG, JPEG, WebP, or TIFF artwork.
- Pick a writable export folder.
- Generate one H.264/AAC MP4 per track at the artwork's native dimensions and aspect ratio.
- Keep the UI responsive and show current-track and overall rendering progress.
- Remember the last selected paths.
- Detect the main bass-energy drop and animate the original punchy zoom-blur effect.
- Turn the bass-reactive zoom blur on or off; when off, the artwork remains static.
- Add one promo row per detected audio file and edit each track's start time and duration independently.
- Enable automatic drop detection to populate every start time using a configurable lead-in (default: 2 seconds), or disable it for manual starts.
- See an inline thumbnail of the selected artwork and play the first detected track in the system audio player.
- Clear the complete form and saved selections to start fresh.
- Choose artwork-native, vertical, square, or landscape output profiles.
- Configure per-track duration plus shared frame rate, CRF quality, encoding speed, and audio bitrate.
- Cancel active rendering safely; partial outputs are removed.
- Review job size/duration estimates before starting.

## Livestream Clips tab

- Pick a long MP4, MOV, M4V, MKV, AVI, or WebM recording.
- Add as many clip rows as needed.
- Enter timestamps as `HH:MM:SS`, `MM:SS`, or plain seconds.
- Give each clip a start plus either an optional end or a duration.
- Default duration is 60 seconds for Instagram-style clips.
- Export accurately timed, broadly compatible H.264/AAC MP4 files.
- Follow overall FFmpeg progress while clips are rendered.
- Play the selected source recording in the system video player before cutting.
- Clear the source, export folder, timestamps, progress, and saved selections.
- Give every clip a descriptive title and cancel active clip creation safely.
- Preview video in the app, scrub the timeline, and set clip start/end from the current playhead.

## Converter tab

- Select one or many audio files and convert them to MP3, WAV, AIFF, FLAC, M4A, AAC, or OGG.
- Choose 128, 192, 256, or 320 kbps when MP3 is the selected output format.
- Select one or many video files and convert them to MP4, MOV, MKV, AVI, or WebM.
- Automatically detect audio versus video and prevent incompatible mixed batches.
- Preview selected inputs, choose a writable export folder, follow progress, and cancel safely.
- Preserve original filenames while applying the shared overwrite, skip, or numbered-copy policy.

## About tab

Displays the transparent full brand lockup, current application version, open-source description, and GitHub repository link.

## Settings tab

- Choose a default export folder shared by all tools.
- Enable or disable completion popups with **Notify when finished**.
- Customize promo/clip filename templates and choose overwrite, skip, or numbered-copy behavior.

## History tab

Stores up to 20 recent jobs in local OS application settings. Jobs can be loaded back into their tool and their output folder can be reopened. History data is never committed to the repository.

## Run on macOS during development

Requirements: Python 3.11+. Installing a system FFmpeg is recommended for development; the packaged app can fall back to its bundled media binary.

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m media_tools_for_record_labels
```

Rendering large native-resolution artwork at 24 fps for 60 seconds can be compute-heavy.

## Build the macOS app

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
open "dist/Media Tools for Record Labels.app"
```

The first unsigned build may need to be opened with Control-click → Open. Distribution to other Macs should add Apple signing and notarization. The build includes `imageio-ffmpeg` as a fallback, while preferring an FFmpeg installation already available on the machine.

Main-branch releases produce both a ZIP and native DMG. When macOS certificate/notarization secrets are configured, the release workflow signs and notarizes the app without storing credentials in the repository.

## Windows path

The engine and UI contain no macOS-only APIs. On a Windows machine with Python and FFmpeg installed:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
.\scripts\build_windows.ps1
```

PyInstaller must build each platform on that platform; a Windows executable cannot be produced reliably from macOS. The release workflow builds the Windows package on a Windows GitHub Actions runner.

Main-branch releases produce both a portable ZIP and an Inno Setup `.exe` installer. Optional signing uses the `WINDOWS_CERTIFICATE` and `WINDOWS_CERTIFICATE_PASSWORD` repository secrets; credentials are never stored in this public repository.

## Defaults inherited from the original script

- Artwork-native output resolution (odd dimensions are reduced by one pixel for H.264 compatibility)
- 24 fps
- 60-second snippet
- Snippet begins 2 seconds before the detected drop
- 0.5-second audio and video fades
- H.264 video, AAC audio at 256 kbps
