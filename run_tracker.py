import ctypes
import os
import sys
import traceback
from pathlib import Path


def _crash(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log = Path(os.environ.get("APPDATA", Path.home())) / "RE-Trace" / "crash.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    except OSError:
        pass
    sys.stderr.write(text)
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text[-1500:], "RE:Trace crashed", 0x10)
    sys.exit(1)


sys.excepthook = _crash

try:
    from kh2rt.main import main
except Exception:
    _crash(*sys.exc_info())

main()
