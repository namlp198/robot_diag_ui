"""`rdt app`: the UI in its own native window (pywebview, Windows WebView2) instead of a browser tab.

If a daemon already answers on the port, the window just opens it; otherwise the daemon runs inside this process and stops when the
window is closed (so the probes are released). Same daemon, same UI, same 127.0.0.1-only binding: nothing else changes.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request
from pathlib import Path


def alive(base: str) -> bool:
    try:
        urllib.request.urlopen(base + "/api/status", timeout=1.5).read()
        return True
    except OSError:
        return False


def run(port: int = 8765) -> int:
    try:
        import webview
    except ImportError:
        print("pywebview is not installed: pip install -e .[app]   (or use: rdt serve, and open the page in a browser)")
        return 2
    import uvicorn

    from .daemon import create_app

    base = f"http://127.0.0.1:{port}"
    server = thread = None
    if not alive(base):
        server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning", log_config=None))
        thread = threading.Thread(target=server.run, name="rdt-daemon", daemon=True)
        thread.start()
        for _ in range(100):
            if alive(base):
                break
            time.sleep(0.2)
        else:
            print(f"the daemon did not start on {base}")
            return 1
    webview.settings["ALLOW_DOWNLOADS"] = True  # "Download CSV" in the sweep panel
    webview.create_window("Robot Diag", base, width=1500, height=950, min_size=(1000, 650), background_color="#07060d")
    storage = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "robot_diag_ui" / "webview"  # keeps theme, language, expressions
    try:
        webview.start(private_mode=False, storage_path=str(storage))
    finally:
        if server is not None:
            server.should_exit = True
            thread.join(timeout=10)
    return 0
