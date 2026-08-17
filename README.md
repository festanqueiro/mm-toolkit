<p align="center">
  <img src="assets/mm-toolkit-logo.png" alt="MM Toolkit" width="360">
</p>

# MM Toolkit

**Audio & Video tools for all**

Create and prepare music content from one desktop app:

- Generate music videos from audio and artwork.
- Find the drop, set timestamps, and preview promo clips.
- Cut short clips from livestream recordings.
- Convert audio and video files into common formats.

Available for macOS and Windows.

## Video Generator tab

- Pick one audio file or a folder and immediately verify the supported files found.
- Supports WAV, AIFF, FLAC, MP3, M4A, AAC, and OGG input through FFmpeg.
- Pick and validate a PNG, JPEG, WebP, or TIFF image, or an MP4, MOV, M4V, MKV, AVI, or WebM video.
- Pick a writable export folder.
- Generate one H.264/AAC MP4 per track at the visual's native dimensions and aspect ratio.
- Loop video visuals when they are shorter than the selected audio clip.
- Mute the original video's sound by default, or keep it and mix it with the selected music by clearing **Mute original video sound**.
- Keep the UI responsive and show current-track and overall rendering progress.
- Remember the last selected paths.
- Detect the main bass-energy drop and animate the original punchy zoom-blur effect.
- Turn the bass-reactive zoom blur on or off; when off, the selected image or video is preserved without that effect.
- Enable or disable video and audio fade-in/fade-out independently.
- Add one promo row per detected audio file and edit each track's start time and duration independently.
- Listen to each configured promo clip directly from its Audio timestamps row before rendering.
- Use the ✨ button beside any Start field to analyze that track and propose a drop-based start time with a configurable lead-in.
- See an inline thumbnail of the selected image or the first frame of the selected video.
- Clear the complete form and saved selections to start fresh.
- Choose visual-native, vertical, square, or landscape output profiles.
- Configure per-track duration plus shared frame rate, CRF quality, encoding speed, and audio bitrate.
- Cancel active rendering safely; partial outputs are removed.
- Review job size/duration estimates before starting.
- See the estimated per-video and combined output duration in Output.

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

## Media Converter tab

- Select one or many audio files and convert them to MP3, WAV, AIFF, FLAC, M4A, AAC, or OGG.
- Choose 128, 192, 256, or 320 kbps when MP3 is the selected output format.
- Select one or many video files and convert them to MP4, MOV, MKV, AVI, or WebM.
- Automatically detect audio versus video and prevent incompatible mixed batches.
- Preview selected inputs, choose a writable export folder, follow progress, and cancel safely.
- Preserve original filenames while applying the shared overwrite, skip, or numbered-copy policy.

## About tab

Displays the transparent full brand lockup, current application version, open-source description, and GitHub repository link. When GitHub has a newer semantic release, it also shows a clickable download link to that release.

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
python -m mm_toolkit
```

Rendering large native-resolution images or videos at 24 fps for 60 seconds can be compute-heavy.

## Build the macOS app

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
open "dist/MM Toolkit.app"
```

The first unsigned build may need to be opened with Control-click → Open. Distribution to other Macs should add Apple signing and notarization. The build includes `imageio-ffmpeg` as a fallback, while preferring an FFmpeg installation already available on the machine.

Main-branch releases produce both a ZIP and native DMG. When macOS certificate/notarization secrets are configured, the release workflow signs and notarizes the app without storing credentials in the repository.

Release tags and package filenames use semantic versions from `mm_toolkit.__version__`, starting at `v1.0.0`. Update that single value before publishing a new release.

## Windows path

The engine and UI contain no macOS-only APIs. On a Windows machine with Python and FFmpeg installed:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
.\scripts\build_windows.ps1
```

PyInstaller must build each platform on that platform; a Windows executable cannot be produced reliably from macOS. The release workflow builds the Windows package on a Windows GitHub Actions runner.

Main-branch releases produce both a portable ZIP and an Inno Setup `.exe` installer. Optional signing uses the `WINDOWS_CERTIFICATE` and `WINDOWS_CERTIFICATE_PASSWORD` repository secrets; credentials are never stored in this public repository.
