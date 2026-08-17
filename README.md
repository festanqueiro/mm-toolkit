<p align="center">
  <img src="assets/mm-toolkit-logo.png" alt="MM Toolkit" width="360">
</p>

# MM Toolkit

**Audio & Video tools for all**

Create and prepare music content from one desktop app.

Available for macOS and Windows.

## Features

- **Video Generator:** turn audio plus artwork or video into ready-to-share MP4s, with editable timestamps, clip listening, drop detection, visual effects, fades, and multiple aspect ratios.
- **Media Cutter:** preview audio or video, mark precise start/end points, and export multiple titled clips.
- **Media Converter:** batch-convert common audio and video formats with progress tracking and safe cancellation.
- **Workflow tools:** shared export settings, filename templates, overwrite controls, recent-job history, and update notifications.

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
