# SPDX-License-Identifier: GPL-3.0-only

"""League PhD desktop shell: feeds your live champ select into leaguephd.com."""

__version__ = "0.1.0"


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
    args = parser.parse_args()

    if not args.page_logs:
        # Must be set before QtWebEngine starts. Level 3 = fatal only; hides the
        # stream of SSL handshake errors from the site's ad/tracker requests.
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --log-level=3".strip()

    from PySide6.QtWidgets import QApplication

    from .window import LcuBridge, MainWindow

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

    app = QApplication(sys.argv)
    bridge = LcuBridge(event_log)
    window = MainWindow(bridge)
    window.show()
    bridge.start()
    sys.exit(app.exec())
