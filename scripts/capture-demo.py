"""Capture the real offline GTK preview with synthetic/demo data under Xvfb."""
import os
from pathlib import Path
import sys
import tempfile
import time
from PIL import ImageGrab
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quiettube.ui import QuietTubeApp
from gi.repository import GLib

with tempfile.TemporaryDirectory(prefix='quiettube-public-preview-') as directory:
    app = QuietTubeApp(Path(directory), demo=True)
    app.register(None)
    app.activate()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
            time.sleep(.01)
        window = app.window
        target = Path(__file__).resolve().parents[1] / 'docs/images/quiettube-desktop.png'
        ImageGrab.grab(bbox=(0, 0, window.get_surface().get_width(), window.get_surface().get_height()), xdisplay=os.environ['DISPLAY']).save(target)
        print(target.name)
    finally:
        app.window.close()
        app.quit()
