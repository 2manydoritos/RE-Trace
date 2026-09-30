import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .controller import Controller
from .storage import Store, default_db_path
from .ui import MainWindow, apply_theme


def main():
    ap = argparse.ArgumentParser(description="KH2 Randomizer route tracker")
    ap.add_argument("--demo", action="store_true", help="simulate a run (no game needed, separate history)")
    ap.add_argument("--speed", type=float, default=40.0, help="demo speed multiplier")
    ap.add_argument("--db", help="path to the history database")
    args = ap.parse_args()

    path = args.db or default_db_path().with_name("demo.db" if args.demo else "runs.db")
    if sys.platform == "win32":
        # own taskbar identity, so Windows shows the journal icon instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RETrace.Tracker")
    app = QApplication(sys.argv)
    app.setApplicationName("RE:Trace")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "icons" / "app.ico")))
    apply_theme(app)
    store = Store(path)
    ctl = Controller(store, demo=args.demo, demo_speed=args.speed)
    win = MainWindow(store, ctl)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
