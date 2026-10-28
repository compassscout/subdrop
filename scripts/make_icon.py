"""从 assets/icon.svg 生成 Windows 用的 assets/icon.ico。

用法：uv run --with pillow python scripts/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841
    svg = (ROOT / "assets" / "icon.svg").read_bytes()
    renderer = QSvgRenderer(svg)

    images: list[Image.Image] = []
    for size in SIZES:
        image = QImage(QSize(size, size), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()

        tmp = ROOT / "assets" / f"_icon_{size}.png"
        image.save(str(tmp))
        images.append(Image.open(tmp).convert("RGBA"))
        tmp.unlink()

    target = ROOT / "assets" / "icon.ico"
    images[-1].save(target, sizes=[(s, s) for s in SIZES])
    print("wrote", target, target.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
