# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

project_root = Path(SPECPATH).resolve()
package_metadata = copy_metadata("imageio") + copy_metadata("imageio-ffmpeg") + copy_metadata("moviepy")
brand_assets = [
    (str(project_root / "assets" / "media-tools-app-icon.png"), "assets"),
    (str(project_root / "assets" / "Media tools app - just logo no bg.png"), "assets"),
    (str(project_root / "assets" / "Media tools app.png"), "assets"),
    (str(project_root / "assets" / "Media tools app - full logo no bg.png"), "assets"),
    (str(project_root / "assets" / "material-icons"), "assets/material-icons"),
]
app_icon = project_root / "assets" / (
    "media-tools-for-record-labels.ico" if sys.platform == "win32" else "media-tools-for-record-labels.icns"
)

a = Analysis(
    [str(project_root / "run_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=package_metadata + brand_assets,
    hiddenimports=[
        "media_tools_for_record_labels.core",
        "moviepy.audio.fx.AudioFadeIn",
        "moviepy.audio.fx.AudioFadeOut",
        "moviepy.video.fx.FadeIn",
        "moviepy.video.fx.FadeOut",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Media Tools for Record Labels",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(app_icon),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="Media Tools for Record Labels")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Media Tools for Record Labels.app",
        icon=str(app_icon),
        bundle_identifier="com.recordlabelmediatools.app",
        info_plist={"NSHighResolutionCapable": True},
    )
