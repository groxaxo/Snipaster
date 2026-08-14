"""Render the project SVG icon to a multi-size Windows ICO file."""

from pathlib import Path

from PIL import Image
from PyQt5.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer


root = Path(__file__).resolve().parents[1]
source = root / "assets" / "snipaster-icon.svg"
destination = root / "assets" / "snipaster.ico"

renderer = QSvgRenderer(str(source))
image = QImage(256, 256, QImage.Format_ARGB32)
image.fill(0)
painter = QPainter(image)
renderer.render(painter, QRectF(0, 0, 256, 256))
painter.end()

data = QByteArray()
buffer = QBuffer(data)
buffer.open(QIODevice.WriteOnly)
image.save(buffer, "PNG")
buffer.close()

with Image.open(__import__("io").BytesIO(bytes(data))) as rendered:
    rendered.save(
        destination,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

print(destination)
