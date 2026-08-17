# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata
from mm_toolkit import __version__

project_root = Path(SPECPATH).resolve()
package_metadata = copy_metadata("imageio") + copy_metadata("imageio-ffmpeg") + copy_metadata("moviepy")
brand_assets = [
    (str(project_root / "assets" / "mm-toolkit-icon.png"), "assets"),
    (str(project_root / "assets" / "mm-toolkit-logo.png"), "assets"),
    (str(project_root / "assets" / "material-icons"), "assets/material-icons"),
]
app_icon = project_root / "assets" / (
    "mm-toolkit.ico" if sys.platform == "win32" else "mm-toolkit.icns"
)

a = Analysis(
    [str(project_root / "run_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=package_metadata + brand_assets,
    hiddenimports=[
        "mm_toolkit.core",
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
    name="MM Toolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(app_icon),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="MM Toolkit")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MM Toolkit.app",
        icon=str(app_icon),
        bundle_identifier="com.mmtoolkit.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
        },
    )
