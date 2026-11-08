"""Animated weather overlays for the Muv window.

Two transparent layers sit above the wallpaper:
  * FogLayer   - drifting fog, *under* the clock and panels so the text stays crisp.
  * FrontLayer - rain streaks, drops on the "glass" and lightning, *over* everything.

Each layer only runs its timer (and is only shown) while an effect needs it, so clear
weather costs nothing. The simulations live in effect_models.py.
"""

import logging
import random
import time
from typing import Optional

from PyQt6.QtCore import QLineF, QPointF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .effect_models import NONE, DropField, EffectSpec, FogModel, LightningModel, RainField

log = logging.getLogger(__name__)

FOG_MAX_FPS = 12  # fog drifts slowly, so it needs far fewer frames than rain
MAX_FRAME_SECONDS = 0.1  # after a stall, do not let the animation jump


class _EffectLayer(QWidget):
    """A transparent, click-through widget that animates while its effect is active."""

    def __init__(self, parent, fps: int):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fps = max(5, min(60, int(fps)))
        self.spec: EffectSpec = NONE
        self._scale = 1.0
        self._last_tick: Optional[float] = None
        self._timer = QTimer(self)
        self._timer.setInterval(round(1000 / self.fps))
        self._timer.timeout.connect(self._tick)
        self.hide()

    # -- subclasses -------------------------------------------------------
    def wants(self, spec: EffectSpec) -> bool:
        raise NotImplementedError

    def rebuild(self) -> None:
        raise NotImplementedError

    def advance(self, dt: float) -> None:
        raise NotImplementedError

    # -- common -----------------------------------------------------------
    def _refresh_scale(self) -> None:
        self._scale = max(self.height(), 360) / 1080.0

    def set_spec(self, spec: EffectSpec) -> None:
        if spec == self.spec:
            return
        self.spec = spec
        self._refresh_scale()  # Qt delays resize events for hidden widgets, so do not rely on resizeEvent
        self.rebuild()
        if self.wants(spec):
            self._last_tick = None
            self.show()
            self._timer.start()
        else:
            self._timer.stop()
            self.hide()

    def resizeEvent(self, event) -> None:
        self._refresh_scale()
        self.rebuild()
        super().resizeEvent(event)

    def _tick(self) -> None:
        now = time.monotonic()
        dt = 0.0 if self._last_tick is None else min(MAX_FRAME_SECONDS, now - self._last_tick)
        self._last_tick = now
        self.advance(dt)
        self.update()


class FrontLayer(_EffectLayer):
    """Rain, raindrops on the glass, and lightning."""

    def __init__(self, parent, fps: int):
        super().__init__(parent, fps)
        self._rain: Optional[RainField] = None
        self._drops: Optional[DropField] = None
        self._lightning: Optional[LightningModel] = None

    def wants(self, spec: EffectSpec) -> bool:
        return bool(spec.rain or spec.drops or spec.lightning)

    def rebuild(self) -> None:
        w, h, s, spec = self.width(), self.height(), self._scale, self.spec
        sized = w > 0 and h > 0
        self._rain = RainField(spec.rain, w, h, s) if spec.rain and sized else None
        self._drops = DropField(spec.drops, w, h, s) if spec.drops and sized else None
        self._lightning = LightningModel() if spec.lightning else None

    def advance(self, dt: float) -> None:
        for model in (self._rain, self._drops, self._lightning):
            if model is not None:
                model.step(dt)

    def paintEvent(self, event) -> None:
        if not (self._rain or self._drops or self._lightning):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._rain:
            self._paint_rain(painter)
        if self._drops:
            self._paint_drops(painter)
        if self._lightning:
            self._paint_lightning(painter)
        painter.end()

    def _paint_rain(self, painter) -> None:
        thin, thick = [], []
        for x1, y1, x2, y2, heavy in self._rain.segments():
            (thick if heavy else thin).append(QLineF(x1, y1, x2, y2))
        # Two pen widths, drawn as batches: much cheaper than one pen per streak.
        for lines, width, alpha in ((thin, 1.2, 90), (thick, 2.2, 130)):
            if lines:
                pen = QPen(QColor(205, 220, 240, alpha), max(1.0, width * self._scale),
                           Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLines(lines)

    def _paint_drops(self, painter) -> None:
        for d in self._drops.drops:
            a = d.alpha()
            if a <= 0:
                continue
            r = d.current_radius()
            if d.trail_from is not None and d.y > d.trail_from:  # the streak a sliding drop leaves behind
                painter.setPen(QPen(QColor(255, 255, 255, int(40 * a)), max(1.0, r * 0.5),
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(d.x, d.trail_from), QPointF(d.x, d.y))
            # the drop: a faint body with a brighter rim, slightly taller than wide...
            painter.setPen(QPen(QColor(255, 255, 255, int(120 * a)), max(1.0, 1.4 * self._scale)))
            painter.setBrush(QColor(255, 255, 255, int(35 * a)))
            painter.drawEllipse(QPointF(d.x, d.y), r, r * 1.2)
            # ...and a small highlight, which is what makes it read as water
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, int(170 * a)))
            painter.drawEllipse(QPointF(d.x - r * 0.3, d.y - r * 0.4), r * 0.28, r * 0.2)

    def _paint_lightning(self, painter) -> None:
        flash = self._lightning.flash
        if flash > 0:
            painter.fillRect(self.rect(), QColor(235, 240, 255, int(150 * flash)))
        alpha, bolt = self._lightning.bolt_alpha, self._lightning.bolt
        if alpha > 0 and bolt:
            w, h = self.width(), self.height()
            polyline = QPolygonF([QPointF(x * w, y * h) for x, y in bolt])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for width, strength in ((12.0, 50), (5.0, 130), (2.2, 255)):  # glow, body, core
                painter.setPen(QPen(QColor(235, 240, 255, int(strength * alpha)),
                                    max(1.0, width * self._scale), Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPolyline(polyline)


class FogLayer(_EffectLayer):
    """Two soft, tiling fog textures drifting in opposite directions."""

    def __init__(self, parent, fps: int):
        super().__init__(parent, min(fps, FOG_MAX_FPS))
        self._model: Optional[FogModel] = None
        self._textures = []

    def wants(self, spec: EffectSpec) -> bool:
        return spec.fog > 0

    def rebuild(self) -> None:
        w, h = self.width(), self.height()
        if not self.wants(self.spec) or w <= 0 or h <= 0:
            self._model, self._textures = None, []
            return
        self._textures = [self._make_texture(w, h, seed) for seed in (1, 2)]
        self._model = FogModel(w, self._scale)

    @staticmethod
    def _make_texture(w: int, h: int, seed: int) -> QPixmap:
        """Soft overlapping blobs, drawn once; repeated at +-width so the texture tiles seamlessly."""
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        rng = random.Random(seed)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for _ in range(14):
            cx, cy = rng.uniform(0, w), rng.uniform(0.15 * h, h)
            radius = rng.uniform(0.18, 0.4) * w
            for dx in (-w, 0, w):
                if cx + dx + radius < 0 or cx + dx - radius > w:
                    continue  # this copy is entirely off-screen
                painter.save()
                painter.translate(cx + dx, cy)
                painter.scale(1.0, 0.45)  # flatten the blobs into wisps
                gradient = QRadialGradient(QPointF(0, 0), radius)
                gradient.setColorAt(0.0, QColor(238, 242, 248, 95))
                gradient.setColorAt(1.0, QColor(238, 242, 248, 0))
                painter.setBrush(QBrush(gradient))
                painter.drawEllipse(QPointF(0, 0), radius, radius)
                painter.restore()
        painter.end()
        return pixmap

    def advance(self, dt: float) -> None:
        if self._model is not None:
            self._model.step(dt)

    def paintEvent(self, event) -> None:
        if self._model is None:
            return
        painter = QPainter(self)
        w = self.width()
        for texture, offset, strength in zip(self._textures, self._model.offsets, FogModel.OPACITIES):
            painter.setOpacity(min(1.0, self.spec.fog * strength))
            x = int(offset)
            painter.drawPixmap(x - w, 0, texture)
            painter.drawPixmap(x, 0, texture)
        painter.end()
