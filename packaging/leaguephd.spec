# -*- mode: python ; coding: utf-8 -*-
# Build: uv run pyinstaller packaging/leaguephd.spec --noconfirm
# Output: dist/LeaguePhD/LeaguePhD.exe (zip the whole dist/LeaguePhD folder to share)
#
# One-folder build on purpose: QtWebEngine is ~200 MB, and a one-file exe
# would unpack all of it to a temp folder on every launch.

from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "leaguephd_shell"

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(PKG / "icon.ico"), "leaguephd_shell"),
        (str(ROOT / "LICENSE"), "."),
    ],
    # Qt modules we don't use; keeps the build smaller.
    excludes=["PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtQuick3D", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
              "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtSerialPort", "tkinter"],
    noarchive=False,
)


def _keep(dest: str) -> bool:
    """Drop Qt payload this app never uses (~150 MB)."""
    p = dest.replace("\\", "/")
    if "qtwebengine_devtools_resources" in p:  # browser devtools
        return False
    if p.endswith(".debug.pak"):  # debug-symbol copies of the resource packs
        return False
    if "/qtwebengine_locales/" in p:  # Chromium UI strings: English is enough
        return p.endswith("/en-US.pak")
    if p.startswith("PySide6/translations/"):  # Qt's own translations
        return False
    if p.startswith("PySide6/qml/"):  # QML runtime; this is a widgets app
        return False
    return True


a.datas = [d for d in a.datas if _keep(d[0])]
a.binaries = [b for b in a.binaries if _keep(b[0])]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LeaguePhD",
    icon=str(PKG / "icon.ico"),
    console=False,  # windowed app; run from source with --debug to see logs
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LeaguePhD", upx=False)
