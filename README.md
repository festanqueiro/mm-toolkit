# Media Tools for Record Labels

A macOS-first desktop app for recurring record-label video workflows. The application uses a cross-platform Python/Qt codebase so the same UI can be packaged for Windows later.

The macOS bundle, Windows executable, and application windows use the rounded platform-style Media Tools icon from `assets/`.

## Promo Videos tab

- Pick a music folder and immediately verify how many supported files it contains.
- Supports WAV, AIFF, FLAC, MP3, M4A, AAC, and OGG input through FFmpeg.
- Pick and validate PNG, JPEG, WebP, or TIFF artwork.
- Pick a writable export folder.
- Generate one H.264/AAC MP4 per track at the artwork's native dimensions and aspect ratio.
- Keep the UI responsive and show current-track and overall rendering progress.
- Remember the last selected paths.
- Detect the main bass-energy drop and animate the original punchy zoom-blur effect.
- Turn the bass-reactive zoom blur on or off; when off, the artwork remains static.
- Configure how many seconds before the detected drop the snippet begins (default: 2 seconds).
- See an inline thumbnail of the selected artwork and play the first detected track in the system audio player.
- Clear the complete form and saved selections to start fresh.

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

## About tab

Displays the transparent full brand lockup, current application version, open-source description, and GitHub repository link.

## Settings tab

- Choose a default export folder shared by all tools.
- Enable or disable completion popups with **Notify when finished**.

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

## Windows path

The engine and UI contain no macOS-only APIs. On a Windows machine with Python and FFmpeg installed:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
.\scripts\build_windows.ps1
```

PyInstaller must build each platform on that platform; a Windows executable cannot be produced reliably from macOS. A future release can run this command in a Windows GitHub Actions job and package the result as an installer.

## Defaults inherited from the original script

- Artwork-native output resolution (odd dimensions are reduced by one pixel for H.264 compatibility)
- 24 fps
- 60-second snippet
- Snippet begins 2 seconds before the detected drop
- 0.5-second audio and video fades
- H.264 video, AAC audio at 256 kbps
