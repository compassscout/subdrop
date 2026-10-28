"""占位页：功能留位置，但坦白说还没做。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .widgets import Card, muted, page_title, subtitle


class PlaceholderPage(QWidget):
    def __init__(
        self,
        title: str,
        tagline: str,
        plan: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(14)

        layout.addWidget(page_title(title))
        layout.addWidget(subtitle(tagline))

        card = Card()
        card.layout.setSpacing(8)

        badge = QLabel("规划中 · 尚未实现")
        badge.setStyleSheet(
            "color:#b45309;background:#fff7e6;border:1px solid #fde2b3;"
            "border-radius:6px;padding:3px 8px;font-size:11px;"
        )
        badge.setFixedWidth(120)
        badge.setAlignment(Qt.AlignCenter)
        card.layout.addWidget(badge)
        card.layout.addSpacing(4)

        for item in plan:
            row = QLabel(f"·  {item}")
            row.setObjectName("statValue")
            row.setWordWrap(True)
            card.layout.addWidget(row)

        card.layout.addSpacing(6)
        card.layout.addWidget(
            muted("这个版本只做「本地视频 → 字幕」。功能列在这里是为了让你知道方向，不是为了凑数。")
        )
        layout.addWidget(card)
        layout.addStretch(1)
