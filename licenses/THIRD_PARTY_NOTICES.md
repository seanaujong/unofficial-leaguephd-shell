# Third-party notices

Unofficial League PhD (leaguephd-shell) is licensed under GPL-3.0-only (see `LICENSE`).
The Windows build bundles the components below. Their full licence texts are in
this `licenses/` folder (Python packages under `licenses/<package>-<version>/`;
those folder names give the exact versions in a given build, and the versions
below may lag behind them).

| Component | Version | Licence | Source |
|---|---|---|---|
| leaguephd-app (original app this is derived from) | — | GPL-3.0 | https://github.com/leaguephd/leaguephd-app |
| League PhD logo (`icon.ico`, from leaguephd-app) | — | GPL-3.0 (file); the logo and the name "League PhD" belong to League PhD | https://github.com/leaguephd/leaguephd-app/tree/master/assets |
| Qt for Python (PySide6, shiboken6) and Qt 6 libraries | 6.12.0 | LGPL-3.0-only (`LGPL-3.0.txt` + `LICENSE`) | https://code.qt.io/cgit/pyside/pyside-setup.git/ , https://download.qt.io/official_releases/qt/ |
| Qt WebEngine (includes Chromium) | 6.12.0 | LGPL-3.0-only; Chromium and its third-party code under BSD-style and other open-source licences | https://doc.qt.io/qt-6/qtwebengine-licensing.html , https://code.qt.io/cgit/qt/qtwebengine-chromium.git/ |
| CPython (includes OpenSSL, libffi, bzip2, xz, expat and others) | 3.12 | PSF-2.0 and bundled licences (`licenses/python/LICENSE.txt`) | https://github.com/python/cpython |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | https://github.com/aio-libs/aiohttp |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 | https://github.com/aio-libs/aiohappyeyeballs |
| aiosignal | 1.4.0 | Apache-2.0 | https://github.com/aio-libs/aiosignal |
| attrs | 26.1.0 | MIT | https://github.com/python-attrs/attrs |
| frozenlist | 1.8.0 | Apache-2.0 | https://github.com/aio-libs/frozenlist |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| multidict | 7.2.1 | Apache-2.0 | https://github.com/aio-libs/multidict |
| propcache | 0.5.4 | Apache-2.0 | https://github.com/aio-libs/propcache |
| psutil | 7.2.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| typing-extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| yarl | 1.25.1 | Apache-2.0 | https://github.com/aio-libs/yarl |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception | https://github.com/pyinstaller/pyinstaller |
| Microsoft Visual C++ runtime (`VCRUNTIME140*.dll`, `MSVCP140*.dll`) | — | Microsoft redistributable runtime | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist |

## Replacing the Qt libraries (LGPL)

Qt is dynamically linked: the Qt DLLs sit unmodified in `_internal/PySide6/`, and
you may replace them with your own builds of the same Qt version. The complete
source of this app, and the build script that produced this package
(`packaging/leaguephd.spec`), are at https://github.com/seanaujong/leaguephd-shell.

## Riot Games

Unofficial League PhD isn't endorsed by Riot Games and doesn't reflect the views
or opinions of Riot Games or anyone officially involved in producing or managing
Riot Games properties. Riot Games, and all associated properties are trademarks
or registered trademarks of Riot Games, Inc.

## League PhD

This app is not made or endorsed by League PhD (leaguephd.com). It displays the
leaguephd.com website, whose content and recommendations belong to League PhD.
