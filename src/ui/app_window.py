"""Main window for Muv: wallpaper background with clock, weather and bus panels."""

import html
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from PyQt6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

log = logging.getLogger(__name__)

CLOCK_PX = 150            # main clock font size at 1080p
SECONDARY_CLOCK_RATIO = 4  # the 24-hour clock is 1/4 the size of the main clock
MAX_BUS_ROWS = 8
FORECAST_SLOTS = 4  # OpenWeatherMap forecasts are 3-hourly, so this covers ~12 hours
MUTED = "#9aa4b2"
UNIT_SYMBOLS = {"metric": "\u00b0C", "imperial": "\u00b0F"}


class BackgroundWidget(QWidget):
    """Paints a wallpaper scaled to cover the widget, cross-fading between images."""

    def __init__(self, fade_ms: int, parent=None):
        super().__init__(parent)
        self._source: Optional[QImage] = None
        self._current: Optional[QPixmap] = None
        self._previous: Optional[QPixmap] = None
        self._opacity = 1.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(max(0, int(fade_ms)))
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.valueChanged.connect(self._on_fade_step)
        self._animation.finished.connect(self._on_fade_done)

    def set_image(self, path: str) -> bool:
        image = QImage(path)
        if image.isNull():
            return False
        self._animation.stop()
        self._previous = self._current if self._animation.duration() > 0 else None
        self._source = image
        self._current = self._cover(image)
        if self._previous is None:
            self._opacity = 1.0
            self.update()
        else:
            self._opacity = 0.0
            self._animation.start()
        return True

    def _cover(self, image: QImage) -> QPixmap:
        size = self.size()
        if size.isEmpty():
            return QPixmap.fromImage(image)
        scaled = image.scaled(
            size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        x = (scaled.width() - size.width()) // 2
        y = (scaled.height() - size.height()) // 2
        return QPixmap.fromImage(scaled.copy(x, y, size.width(), size.height()))

    def _on_fade_step(self, value) -> None:
        self._opacity = float(value)
        self.update()

    def _on_fade_done(self) -> None:
        self._previous = None  # free the old pixmap
        self._opacity = 1.0
        self.update()

    def resizeEvent(self, event) -> None:
        if self._source is not None:
            self._animation.stop()
            self._previous = None
            self._opacity = 1.0
            self._current = self._cover(self._source)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16))
        if self._previous is not None:
            painter.drawPixmap(0, 0, self._previous)
        if self._current is not None:
            painter.setOpacity(self._opacity)
            painter.drawPixmap(0, 0, self._current)
        painter.end()


class AppWindow(QWidget):
    """Slots (update_time/update_weather/update_bus/update_background/set_error) run on the GUI thread."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        display = config.section("display")
        self._time_format = display["time_format"]
        self._secondary_time_format = display["secondary_time_format"]  # "" hides the second clock
        self._clock_gap = display["clock_gap"]  # extra px (at 1080p) between the two clocks
        self._date_format = display["date_format"]
        self._fullscreen = bool(display["fullscreen"])
        self._unit = UNIT_SYMBOLS.get(config.get("weather.units"), "K")
        self._errors: Dict[str, str] = {}
        self._last_weather: Optional[Dict[str, Any]] = None
        self._last_bus: Optional[Dict[str, Any]] = None
        self._time_key = None
        self._scale = 1.0

        self.setWindowTitle("Muv")
        if display["hide_cursor"]:
            self.setCursor(Qt.CursorShape.BlankCursor)

        self.background = BackgroundWidget(display["fade_ms"], self)
        self.content = QWidget(self)  # created after the background, so it stacks on top

        self.time_label = QLabel(objectName="time")
        self.time24_label = QLabel(objectName="time24")
        self.date_label = QLabel(objectName="date")
        self.weather_title = QLabel("Weather", objectName="panelTitle")
        self.weather_body = QLabel(objectName="body")
        self.bus_title = QLabel("Buses", objectName="panelTitle")
        self.bus_body = QLabel(objectName="body")
        self.status_label = QLabel(objectName="status")
        for label in (self.weather_body, self.bus_body):
            label.setTextFormat(Qt.TextFormat.RichText)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        if not self._secondary_time_format:
            self.time24_label.hide()

        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        clock_box.addWidget(self.time_label)
        clock_box.addWidget(self.time24_label)
        clock_box.addWidget(self.date_label)
        clock_box.addStretch()

        weather_panel = self._panel(self.weather_title, self.weather_body)
        top = QHBoxLayout()
        top.addLayout(clock_box)
        top.addStretch()
        top.addWidget(weather_panel, 0, Qt.AlignmentFlag.AlignTop)

        self.root = QVBoxLayout(self.content)
        self.root.addLayout(top)
        self.root.addStretch()
        self.root.addWidget(self._panel(self.bus_title, self.bus_body))
        self.root.addWidget(self.status_label)

        self.update_time()
        self._render_weather()
        self._render_bus()
        self._apply_scale()

    @staticmethod
    def _panel(title: QLabel, body: QLabel) -> QFrame:
        frame = QFrame(objectName="panel")
        layout = QVBoxLayout(frame)
        layout.addWidget(title)
        layout.addWidget(body)
        return frame

    # ---- presentation --------------------------------------------------
    def present(self) -> None:
        if self._fullscreen:
            self.showFullScreen()
        else:
            self.resize(1280, 720)
            self.show()

    def resizeEvent(self, event) -> None:
        self.background.setGeometry(self.rect())
        self.content.setGeometry(self.rect())
        self._apply_scale()
        super().resizeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)

    def _px(self, value: float) -> int:
        return max(1, round(value * self._scale))

    def _apply_scale(self) -> None:
        """Scale fonts and spacing with window height (designed at 1080p)."""
        self._scale = max(self.height(), 360) / 1080.0
        px = self._px
        self.setStyleSheet(
            f"""
            QLabel {{ color: #f4f6fa; background: transparent; }}
            QFrame#panel {{ background-color: rgba(8, 12, 20, 165); border-radius: {px(18)}px; }}
            QLabel#date {{ font-size: {px(38)}px; }}
            QLabel#panelTitle {{ font-size: {px(24)}px; color: {MUTED}; }}
            QLabel#body {{ font-size: {px(30)}px; }}
            QLabel#status {{ font-size: {px(22)}px; color: #ffb4a8; }}
            """
        )
        margin = px(48)
        self.root.setContentsMargins(margin, margin, margin, margin)
        self.root.setSpacing(px(16))
        self._style_clock()
        for panel in self.content.findChildren(QFrame, "panel"):
            panel.layout().setContentsMargins(px(28), px(20), px(28), px(20))
        self._render_weather()
        self._render_bus()

    def _style_clock(self) -> None:
        """Size both clocks and pull the 24-hour clock up under the main one.

        A big font's line box has a lot of empty space below the digits (room for
        descenders that digits and AM/PM never use). Cutting the main clock's height
        down to its ascent plus a small gap removes that space.
        """
        main_font = QFont(self.time_label.font())
        main_font.setPixelSize(self._px(CLOCK_PX))
        main_font.setWeight(QFont.Weight.DemiBold)
        self.time_label.setFont(main_font)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        gap = round(self._clock_gap * self._scale)  # not _px(): 0 must stay 0
        self.time_label.setFixedHeight(QFontMetrics(main_font).ascent() + gap)

        small_font = QFont(self.time24_label.font())
        small_font.setPixelSize(self._px(CLOCK_PX / SECONDARY_CLOCK_RATIO))
        self.time24_label.setFont(small_font)

    # ---- slots ---------------------------------------------------------
    @staticmethod
    def _format_clock(now: datetime, fmt: str) -> str:
        text = now.strftime(fmt)
        if "%p" in fmt:
            text = text.upper()  # some locales give "pm"; show "PM"
        if "%I" in fmt:
            text = text.lstrip("0")  # 09:05 PM -> 9:05 PM
        return text

    def update_time(self) -> None:
        now = datetime.now()
        main = self._format_clock(now, self._time_format)
        secondary = self._format_clock(now, self._secondary_time_format) if self._secondary_time_format else ""
        if (main, secondary) != self._time_key:  # skip redundant repaints
            self._time_key = (main, secondary)
            self.time_label.setText(main)
            self.time24_label.setText(secondary)
            self.date_label.setText(now.strftime(self._date_format))

    def update_weather(self, payload: Dict[str, Any]) -> None:
        self._last_weather = payload
        self.clear_error("weather")
        self._render_weather()

    def update_bus(self, payload: Dict[str, Any]) -> None:
        self._last_bus = payload
        errors = payload.get("errors") or []
        if errors:
            self.set_error("bus", "; ".join(errors))
        else:
            self.clear_error("bus")
        self._render_bus()

    def update_background(self, path: str) -> None:
        if not self.background.set_image(path):
            log.warning("Could not load wallpaper %s", path)

    def set_error(self, source: str, message: str) -> None:
        self._errors[source] = message
        self._show_errors()

    def clear_error(self, source: str) -> None:
        if self._errors.pop(source, None) is not None:
            self._show_errors()

    def _show_errors(self) -> None:
        text = "  \u2022  ".join(html.escape(m) for m in self._errors.values())
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

    # ---- rendering -----------------------------------------------------
    def _temp(self, value) -> str:
        return f"{value:.0f}{self._unit}" if isinstance(value, (int, float)) else "--"

    def _render_weather(self) -> None:
        px = self._px
        current = (self._last_weather or {}).get("current")
        if self._last_weather is None:
            self.weather_body.setText("Loading\u2026")
            return
        if not current:
            self.weather_body.setText("Weather unavailable")
            return

        main = current.get("main") or {}
        conditions = (current.get("weather") or [{}])[0]
        description = html.escape(str(conditions.get("description", "")).capitalize())
        city = html.escape(str(current.get("name", "")))
        humidity = main.get("humidity")
        details = [part for part in (
            city,
            f"Feels like {self._temp(main.get('feels_like'))}",
            f"Humidity {humidity:.0f}%" if isinstance(humidity, (int, float)) else "",
        ) if part]

        parts = [
            f'<div style="font-size:{px(72)}px; font-weight:600">{self._temp(main.get("temp"))}</div>',
            f'<div style="font-size:{px(32)}px">{description}</div>',
            f'<div style="font-size:{px(22)}px; color:{MUTED}">{" &middot; ".join(details)}</div>',
        ]

        slots = ((self._last_weather.get("forecast") or {}).get("list") or [])[:FORECAST_SLOTS]
        cells = []
        for slot in slots:
            try:
                when = datetime.fromtimestamp(slot["dt"]).strftime("%H:%M")
            except (KeyError, TypeError, ValueError, OSError):
                continue
            cells.append(
                f'<td align="center" style="padding-right:{px(24)}px">'
                f'<span style="font-size:{px(22)}px; color:{MUTED}">{when}</span><br>'
                f'<span style="font-size:{px(28)}px">{self._temp((slot.get("main") or {}).get("temp"))}</span></td>'
            )
        if cells:
            parts.append(f'<table style="margin-top:{px(10)}px"><tr>{"".join(cells)}</tr></table>')
        self.weather_body.setText("".join(parts))

    @staticmethod
    def _eta_text(arrival: Dict[str, Any]) -> str:
        minutes = arrival.get("minutes")
        if minutes is None:
            return html.escape(arrival.get("remark") or "\u2014")
        return "Due" if minutes <= 0 else f"{minutes} min"

    def _render_bus(self) -> None:
        px = self._px
        if self._last_bus is None:
            self.bus_body.setText("Loading\u2026")
            return
        if not self._last_bus.get("stops_configured", True):
            self.bus_body.setText("No bus stops configured (see config.json)")
            return
        arrivals = (self._last_bus.get("arrivals") or [])[:MAX_BUS_ROWS]
        if not arrivals:
            self.bus_body.setText("No upcoming buses")
            return

        rows = []
        for arrival in arrivals:
            label = html.escape(arrival.get("label") or "")
            where = f'<span style="color:{MUTED}; font-size:{px(22)}px"> {label}</span>' if label else ""
            rows.append(
                "<tr>"
                f'<td style="padding-right:{px(24)}px"><b>{html.escape(str(arrival.get("route", "")))}</b></td>'
                f'<td style="padding-right:{px(24)}px">{html.escape(arrival.get("destination") or "")}{where}</td>'
                f'<td align="right">{self._eta_text(arrival)}</td>'
                "</tr>"
            )
        self.bus_body.setText(f"<table>{''.join(rows)}</table>")
