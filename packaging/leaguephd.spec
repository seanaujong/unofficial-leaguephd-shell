# -*- mode: python ; coding: utf-8 -*-
# Build: uv run pyinstaller packaging/leaguephd.spec --noconfirm
# Output: dist/UnofficialLeaguePhd/UnofficialLeaguePhd.exe
#         (zip the whole dist/UnofficialLeaguePhd folder to share)
#
# One-folder build on purpose: QtWebEngine is ~200 MB, and a one-file exe
# would unpack all of it to a temp folder on every launch. It also keeps the
# Qt DLLs as separate, replaceable files, as the LGPL requires.

import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "leaguephd_shell"
INIT = (PKG / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__ = "([^"]+)"', INIT).group(1)
APP_NAME = re.search(r'APP_NAME = "([^"]+)"', INIT).group(1)
EXE_NAME = "UnofficialLeaguePhd"

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(PKG / "icon.ico"), "leaguephd_shell")],
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

# Shown in the exe's Properties > Details. SignPath requires ProductName to be
# the project's name and consistent across builds.
_v = tuple(int(x) for x in (VERSION.split(".") + ["0"] * 4)[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", APP_NAME),
            StringStruct("FileDescription", f"{APP_NAME} (not affiliated with League PhD or Riot Games)"),
            StringStruct("CompanyName", "leaguephd-shell contributors"),
            StringStruct("LegalCopyright", "GPL-3.0-only. Derived from leaguephd-app by leaguephd."),
            StringStruct("OriginalFilename", f"{EXE_NAME}.exe"),
            StringStruct("InternalName", EXE_NAME),
            StringStruct("ProductVersion", VERSION),
            StringStruct("FileVersion", VERSION),
            StringStruct("Comments", "https://github.com/seanaujong/unofficial-leaguephd-shell"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    icon=str(PKG / "icon.ico"),
    version=version_info,
    console=False,  # windowed app; run from source with --debug to see logs
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=EXE_NAME, upx=False)


# --- Licences: a visible licenses/ folder next to the exe ---------------------

def _runtime_distributions(root: str) -> list[metadata.Distribution]:
    """The app's runtime dependency closure (no dev or optional extras)."""
    seen, todo, found = set(), [root], []
    while todo:
        name = todo.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            continue
        seen.add(key)
        dist = metadata.distribution(name)
        found.append(dist)
        for spec in dist.requires or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                todo.append(req.name)
    return found


out = Path(DISTPATH) / EXE_NAME / "licenses"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
shutil.copy2(ROOT / "LICENSE", out.parent / "LICENSE.txt")  # this app's licence, top level
for f in (ROOT / "licenses").iterdir():  # notices + LGPL text
    shutil.copy2(f, out / f.name)
(out / "python").mkdir()
shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", out / "python" / "LICENSE.txt")
for dist in [*_runtime_distributions("leaguephd-shell"), metadata.distribution("pyinstaller")]:
    name = dist.metadata["Name"]
    if name == "leaguephd-shell":
        continue
    files = [f for f in dist.files or []
             if re.search(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", f.name, re.I) and ".dist-info" in str(f)
             # Qt wheels only carry a note for commercial licensees; we use Qt under the LGPL.
             and not f.name.startswith("LicenseRef-Qt-Commercial")]
    is_qt = name.lower().startswith(("pyside6", "shiboken6"))
    if not files and not is_qt:
        continue
    target = out / f"{name}-{dist.version}"
    target.mkdir()
    for f in files:
        shutil.copy2(dist.locate_file(f), target / f.name)
    if is_qt:
        (target / "LICENSE-NOTE.txt").write_text(
            f"{name} {dist.version} is used under the GNU Lesser General Public License v3\n"
            "(LGPL-3.0-only). See ../LGPL-3.0.txt, and ../../LICENSE.txt for the GNU GPL v3\n"
            "text that the LGPL supplements. Source: https://code.qt.io/cgit/pyside/pyside-setup.git/\n",
            encoding="utf-8",
        )
print(f"Licences collected into {out}")
