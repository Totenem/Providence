"""Run inside the app container to verify the display and capture its desktop."""
import socket
import urllib.request
from pathlib import Path

from PySide6.QtGui import QGuiApplication

with urllib.request.urlopen("http://127.0.0.1:6080/vnc.html", timeout=3) as response:
    assert response.status == 200
with socket.create_connection(("127.0.0.1", 5900), timeout=3) as connection:
    assert connection.recv(12).startswith(b"RFB ")
app = QGuiApplication([])
screen = app.primaryScreen()
assert screen is not None
target = Path.home() / "providence-desktop.png"
assert screen.grabWindow(0).save(str(target))
print(f"Browser page, VNC protocol and Qt display verified. Screenshot: {target}")
