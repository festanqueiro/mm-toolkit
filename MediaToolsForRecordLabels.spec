# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

project_root = Path(SPECPATH).resolve()
package_metadata = copy_metadata("imageio") + copy_metadata("imageio-ffmpeg") + copy_metadata("moviepy")

a = Analysis(
    [str(project_root / "run_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=package_metadata,
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
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="Media Tools for Record Labels")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Media Tools for Record Labels.app",
        bundle_identifier="com.recordlabelmediatools.app",
        info_plist={"NSHighResolutionCapable": True},
    )
