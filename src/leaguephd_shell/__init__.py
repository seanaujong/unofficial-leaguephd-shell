# SPDX-License-Identifier: GPL-3.0-only

"""Unofficial League PhD: feeds your live champ select into leaguephd.com.

Not made or endorsed by leaguephd or Riot Games.
"""

__version__ = "0.1.1"
APP_NAME = "Unofficial League PhD"  # shown to users; also the exe's ProductName


def main() -> None:
    import argparse
    import logging
    import os
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="leaguephd-shell")
    parser.add_argument(
        "--debug", action="store_true",
        help="verbose logging, and record raw champ select events to logs/session.jsonl",
    )
    parser.add_argument(
        "--page-logs", action="store_true",
        help="also show the web page's console output and Chromium's network errors",
    )
    parser.add_argument(
        "--no-update-check", action="store_true",
        help="don't ask GitHub at startup whether a newer release exists",
    )
    # Anything we don't recognise goes to Qt (e.g. -qwindowgeometry WxH+X+Y).
    args, qt_args = parser.parse_known_args()

    if not args.page_logs:
        # Must be set before QtWebEngine starts. Level 3 = fatal only; hides the
        # stream of SSL handshake errors from the site's ad/tracker requests.
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --log-level=3".strip()

    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows our icon instead of python.exe's.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("leaguephd-shell.unofficial")

    from PySide6.QtWidgets import QApplication

    from .window import LcuBridge, MainWindow, UpdateChecker

    event_log = None
    if args.debug:
        logs = Path("logs")
        logs.mkdir(exist_ok=True)
        event_log = logs / "session.jsonl"
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("leaguephd_shell.page").setLevel(
        logging.DEBUG if args.page_logs else logging.WARNING
    )

    app = QApplication([sys.argv[0], *qt_args])
    bridge = LcuBridge(event_log)
    window = MainWindow(bridge)
    window.show()
    bridge.start()
    if not args.no_update_check:
        checker = UpdateChecker(__version__)
        checker.found.connect(window.show_update)
        checker.start()
    sys.exit(app.exec())
