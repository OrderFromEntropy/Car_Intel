"""Pixel-art truck animation widget — bounces left-right with suspension bounce."""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

_PS = 3  # screen pixels per art pixel (scale factor)

# Pixel color palette
_C = {
    ".": None,                          # transparent
    "B": QColor(0x1f, 0x6f, 0xeb),     # body blue
    "b": QColor(0x38, 0x8b, 0xfd),     # body highlight
    "W": QColor(0x79, 0xc0, 0xff),     # window glass
    "T": QColor(0x21, 0x26, 0x2d),     # tire (dark)
    "R": QColor(0x8b, 0x94, 0x9e),     # rim / hubcap
    "r": QColor(0x6e, 0x76, 0x81),     # rim shadow
    "L": QColor(0xff, 0xf0, 0x70),     # headlight
    "G": QColor(0x30, 0x36, 0x3d),     # grille
    "X": QColor(0x58, 0xa6, 0xff),     # accent stripe
}

# ── Pixel art: 20 wide × 9 tall, truck FACING RIGHT ──────────────────────────
# Front of truck (headlight/grille) is on the LEFT side.
# Front wheel: cols 2–4   Rear wheel: cols 14–16

_ART_W = 20
_ART_H = 9

# Frame 0 — wheels standard
_F0 = [
    "....BBBBB...........",   # 0  cab roof
    "...BWWWWbBBBBBBBBBB.",   # 1  cab window + bed top
    "..BWWWWWbBBBBBBBBBBB",   # 2  lower cab window + bed
    "LGBBBBBBBBBBBBBBBBb.",   # 3  full body (L=headlight G=grille b=tail)
    "LGBBBBBBBBBBBBBBBBb.",   # 4
    "..XXBBBBBBBBBBBBBBb.",   # 5  lower body with accent stripe
    "..TRT.........TRT...",   # 6  wheels  (T=tire R=rim)
    "..TrT.........TrT...",   # 7  wheel bottom
    "....................",    # 8  ground clearance
]

# Frame 1 — wheels rotated (rim appears to spin)
_F1 = [
    "....BBBBB...........",
    "...BWWWWbBBBBBBBBBB.",
    "..BWWWWWbBBBBBBBBBBB",
    "LGBBBBBBBBBBBBBBBBb.",
    "LGBBBBBBBBBBBBBBBBb.",
    "..XXBBBBBBBBBBBBBBb.",
    "..RrR.........RrR...",   # rim rotated
    "..TRT.........TRT...",
    "....................",
]

# Frame 2 — mid-rotation
_F2 = [
    "....BBBBB...........",
    "...BWWWWbBBBBBBBBBB.",
    "..BWWWWWbBBBBBBBBBBB",
    "LGBBBBBBBBBBBBBBBBb.",
    "LGBBBBBBBBBBBBBBBBb.",
    "..XXBBBBBBBBBBBBBBb.",
    "..rTr.........rTr...",
    "..RrR.........RrR...",
    "....................",
]

_FRAMES = [_F0, _F1, _F2, _F1]   # cycle 0→1→2→1→0…


class TruckAnimationWidget(QWidget):
    """
    Self-contained animated 8-bit truck.
    Call start() to show it driving; stop() to hide.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x: float = 0.0
        self._direction: int = 1       # 1 = right, -1 = left
        self._tick: int = 0
        self._frame_idx: int = 0

        self._timer = QTimer(self)
        self._timer.setInterval(45)    # ~22 fps — smooth but not frenetic
        self._timer.timeout.connect(self._on_tick)

        widget_h = (_ART_H + 3) * _PS  # art height + 3px ground clearance
        self.setFixedHeight(widget_h)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setVisible(False)

    # ── Public ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._x = 0.0
        self._tick = 0
        self._direction = 1
        self.setVisible(True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    # ── Internal ─────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._tick += 1

        # Horizontal movement
        speed = 2.8
        self._x += speed * self._direction

        truck_w = _ART_W * _PS
        max_x = max(0.0, float(self.width() - truck_w))

        if self._direction == 1 and self._x >= max_x:
            self._x = max_x
            self._direction = -1
        elif self._direction == -1 and self._x <= 0:
            self._x = 0.0
            self._direction = 1

        # Advance wheel animation frame every 4 ticks
        if self._tick % 4 == 0:
            self._frame_idx = (self._frame_idx + 1) % len(_FRAMES)

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Vertical suspension bounce:
        #   primary low-freq oscillation  + secondary high-freq micro-jitter
        y_bounce = (
            math.sin(self._tick * 0.28) * 1.8
            + math.sin(self._tick * 1.3) * 0.45
        )

        rows = _FRAMES[self._frame_idx]

        # Mirror the art when driving left
        if self._direction == -1:
            rows = [row[::-1] for row in rows]

        x0 = int(self._x)
        # Vertical offset: 1 * _PS baseline + bounce scaled to screen pixels
        y0 = int(1 * _PS + y_bounce * _PS * 0.5)

        for ri, row in enumerate(rows):
            for ci, ch in enumerate(row):
                color = _C.get(ch)
                if color is None:
                    continue
                painter.fillRect(
                    x0 + ci * _PS,
                    y0 + ri * _PS,
                    _PS,
                    _PS,
                    color,
                )

        painter.end()
