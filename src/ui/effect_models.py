"""Weather effects: which effect matches the weather, and the particle simulations behind them.

Qt-free on purpose so the logic can be tested without a display; weather_effects.py draws it.
All distances are in pixels at 1080p and are multiplied by a ``scale`` for other screen sizes.
"""

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class EffectSpec:
    name: str = "none"
    rain: int = 0            # falling rain: 0 = none, 1 = light/drizzle, 2 = moderate, 3 = heavy
    drops: int = 0           # raindrops on the "glass": 0..3
    lightning: bool = False
    fog: float = 0.0         # opacity (0..1) of the drifting fog layers

    @property
    def active(self) -> bool:
        return bool(self.rain or self.drops or self.lightning or self.fog)


NONE = EffectSpec()

# Selectable with display.weather_preview in config.json to check the effects without waiting for the weather.
PREVIEW_SPECS = {
    "clear": NONE,
    "drizzle": EffectSpec("drizzle", rain=1, drops=1),
    "rain": EffectSpec("rain", rain=2, drops=2),
    "heavy_rain": EffectSpec("heavy_rain", rain=3, drops=3),
    "thunderstorm": EffectSpec("thunderstorm", rain=3, drops=2, lightning=True),
    "mist": EffectSpec("mist", fog=0.35),
    "fog": EffectSpec("fog", fog=0.6),
    "haze": EffectSpec("haze", fog=0.25),
}

# OpenWeatherMap condition ids -> rain level (drizzle 3xx, rain 5xx)
_RAIN_LEVELS = {
    300: 1, 301: 1, 302: 1, 310: 1, 311: 1, 312: 1, 313: 1, 314: 2, 321: 1,
    500: 1, 501: 2, 502: 3, 503: 3, 504: 3, 511: 2, 520: 1, 521: 2, 522: 3, 531: 2,
}
# 7xx "atmosphere" conditions that reduce visibility -> fog opacity
_FOG_LEVELS = {701: 0.35, 711: 0.30, 721: 0.25, 731: 0.30, 741: 0.60, 751: 0.30, 761: 0.30, 762: 0.40}
# Thunderstorm ids with rain: 2xx. The others (210-221) are dry thunderstorms and get light rain.
_STORM_RAIN = {200: 2, 201: 2, 202: 3, 230: 1, 231: 1, 232: 2}


def effect_for_weather(weather_id, group: Optional[str] = None) -> EffectSpec:
    """Pick the effect for an OpenWeatherMap condition id (and, as a fallback, its group name).

    Clear skies, clouds, snow and anything unrecognised show no effect.
    """
    try:
        code = int(weather_id)
    except (TypeError, ValueError):
        code = None

    if code is not None:
        if 200 <= code < 300:
            rain = _STORM_RAIN.get(code, 1)
            return EffectSpec("thunderstorm", rain=rain, drops=min(rain, 2), lightning=True)
        if code in _RAIN_LEVELS:
            level = _RAIN_LEVELS[code]
            return EffectSpec("drizzle" if code < 400 else "rain", rain=level, drops=level)
        if code in _FOG_LEVELS:
            return EffectSpec("fog", fog=_FOG_LEVELS[code])
        if code == 800 or 801 <= code <= 804:
            return NONE

    key = (group or "").strip().lower()
    if key == "thunderstorm":
        return EffectSpec("thunderstorm", rain=2, drops=1, lightning=True)
    if key == "rain":
        return EffectSpec("rain", rain=2, drops=2)
    if key == "drizzle":
        return EffectSpec("drizzle", rain=1, drops=1)
    if key in ("mist", "fog", "haze", "smoke", "dust", "sand", "ash"):
        return EffectSpec("fog", fog=0.35)
    return NONE


# ---- falling rain -----------------------------------------------------------

class _Streak:
    __slots__ = ("x", "y", "length", "speed", "thick")


class RainField:
    """Slanted streaks falling from the top of the screen; respawn above the top when they leave."""

    COUNTS = {1: 90, 2: 200, 3: 360}  # streaks at 1080p
    LENGTHS = {1: (16.0, 28.0), 2: (24.0, 42.0), 3: (34.0, 60.0)}
    SPEEDS = {1: (900.0, 1300.0), 2: (1200.0, 1700.0), 3: (1500.0, 2100.0)}  # px per second
    SLANT = 0.18  # horizontal pixels per vertical pixel

    def __init__(self, level: int, width: float, height: float, scale: float = 1.0,
                 rng: Optional[random.Random] = None):
        self.level = max(1, min(3, int(level)))
        self.width, self.height, self.scale = float(width), float(height), float(scale)
        self.rng = rng or random.Random()
        area = max(0.1, self.width * self.height / (1920 * 1080))
        count = max(10, int(self.COUNTS[self.level] * area))
        self.streaks = [self._spawn(spread=True) for _ in range(count)]

    def _spawn(self, spread: bool) -> _Streak:
        r = self.rng
        s = _Streak()
        s.length = r.uniform(*self.LENGTHS[self.level]) * self.scale
        s.speed = r.uniform(*self.SPEEDS[self.level]) * self.scale
        s.thick = r.random() < 0.3
        s.x = r.uniform(-self.height * self.SLANT, self.width)  # start left of the screen: rain drifts right
        s.y = r.uniform(0, self.height) if spread else -s.length - r.uniform(0, 0.2 * self.height)
        return s

    def step(self, dt: float) -> None:
        for i, s in enumerate(self.streaks):
            s.y += s.speed * dt
            s.x += s.speed * self.SLANT * dt
            if s.y - s.length > self.height or s.x - s.length * self.SLANT > self.width:
                self.streaks[i] = self._spawn(spread=False)

    def segments(self) -> List[Tuple[float, float, float, float, bool]]:
        """(tail_x, tail_y, head_x, head_y, thick) for every streak."""
        return [(s.x - s.length * self.SLANT, s.y - s.length, s.x, s.y, s.thick) for s in self.streaks]


# ---- drops on the glass -----------------------------------------------------

class Drop:
    __slots__ = ("x", "y", "radius", "age", "life", "slide_start", "slide_dur", "slide_speed", "trail_from")
    GROW = 0.6   # seconds to reach full size
    FADE = 2.0   # seconds spent fading out at the end of its life

    def alpha(self) -> float:
        return max(0.0, min(1.0, self.age / self.GROW, (self.life - self.age) / self.FADE))

    def current_radius(self) -> float:
        return self.radius * (0.4 + 0.6 * min(1.0, self.age / self.GROW))


class DropField:
    """Droplets that appear, grow, sometimes slide down leaving a trail, then fade away."""

    MAX = {1: 8, 2: 16, 3: 28}   # simultaneous drops at 1080p
    FILL_SECONDS = 5.0           # time to refill up to the maximum

    def __init__(self, level: int, width: float, height: float, scale: float = 1.0,
                 rng: Optional[random.Random] = None):
        self.level = max(1, min(3, int(level)))
        self.width, self.height, self.scale = float(width), float(height), float(scale)
        self.rng = rng or random.Random()
        area = max(0.1, self.width * self.height / (1920 * 1080))
        self.max_drops = max(3, int(self.MAX[self.level] * area))
        self.drops: List[Drop] = []
        for _ in range(self.max_drops // 2):  # start part-full so the effect is visible immediately
            drop = self._spawn()
            drop.age = self.rng.uniform(0.0, drop.life * 0.6)
            self.drops.append(drop)
        self._budget = 0.0

    def _spawn(self) -> Drop:
        r = self.rng
        d = Drop()
        d.radius = r.uniform(5.0, 14.0) * self.scale
        d.x = r.uniform(0, self.width)
        d.y = r.uniform(0, self.height * 0.9)
        d.age = 0.0
        d.life = r.uniform(7.0, 15.0)
        d.slide_start = r.uniform(2.5, 6.0) if r.random() < 0.4 else math.inf  # most stay put
        d.slide_dur = r.uniform(1.5, 4.0)
        d.slide_speed = r.uniform(30.0, 90.0) * self.scale
        d.trail_from = None
        return d

    def step(self, dt: float) -> None:
        for d in self.drops:
            d.age += dt
            if d.slide_start <= d.age < d.slide_start + d.slide_dur:
                if d.trail_from is None:
                    d.trail_from = d.y
                d.y += d.slide_speed * dt
        self.drops = [d for d in self.drops if d.age < d.life and d.y < self.height + d.radius]

        self._budget += self.max_drops / self.FILL_SECONDS * dt
        while self._budget >= 1.0 and len(self.drops) < self.max_drops:
            self.drops.append(self._spawn())
            self._budget -= 1.0
        self._budget = min(self._budget, 1.0)  # do not bank spawns while full


# ---- lightning --------------------------------------------------------------

class LightningModel:
    """Irregular strikes: a screen flash that decays quickly, plus a jagged bolt that fades."""

    FLASH_DECAY = 0.07   # seconds
    BOLT_SECONDS = 0.3
    STRIKE_SECONDS = 1.0

    def __init__(self, rng: Optional[random.Random] = None,
                 first_delay: Tuple[float, float] = (2.0, 5.0),
                 interval: Tuple[float, float] = (6.0, 14.0)):
        self.rng = rng or random.Random()
        self.interval = interval
        self.t = 0.0
        self.next_strike = self.rng.uniform(*first_delay)
        self.strike_t: Optional[float] = None
        self.peaks: List[Tuple[float, float]] = []   # (offset seconds, brightness)
        self.bolt: List[Tuple[float, float]] = []    # normalised (x, y) points, top to bottom

    def step(self, dt: float) -> None:
        self.t += dt
        if self.strike_t is None:
            if self.t >= self.next_strike:
                self._strike()
        elif self.t - self.strike_t > self.STRIKE_SECONDS:
            self.strike_t = None
            self.bolt = []
            self.next_strike = self.t + self.rng.uniform(*self.interval)

    def _strike(self) -> None:
        r = self.rng
        self.strike_t = self.t
        self.peaks = [(0.0, r.uniform(0.7, 1.0))]
        if r.random() < 0.7:  # most strikes flicker once more
            self.peaks.append((r.uniform(0.1, 0.2), r.uniform(0.4, 0.7)))
        x, y = r.uniform(0.2, 0.8), 0.0
        bottom = r.uniform(0.5, 0.85)
        self.bolt = [(x, y)]
        segments = 12
        for i in range(1, segments + 1):
            x = min(0.98, max(0.02, x + r.uniform(-0.04, 0.04)))
            self.bolt.append((x, bottom * i / segments))

    @property
    def flash(self) -> float:
        """Screen-flash brightness, 0..1."""
        if self.strike_t is None:
            return 0.0
        elapsed = self.t - self.strike_t
        levels = [p * math.exp(-(elapsed - t0) / self.FLASH_DECAY) for t0, p in self.peaks if elapsed >= t0]
        return min(1.0, max(levels, default=0.0))

    @property
    def bolt_alpha(self) -> float:
        if self.strike_t is None:
            return 0.0
        elapsed = self.t - self.strike_t
        return max(0.0, 1.0 - elapsed / self.BOLT_SECONDS)


# ---- fog --------------------------------------------------------------------

class FogModel:
    """Two fog layers drifting horizontally in opposite directions, wrapping around."""

    SPEEDS = (14.0, -8.0)      # px per second at 1080p
    OPACITIES = (1.0, 0.7)     # relative strength of each layer

    def __init__(self, width: float, scale: float = 1.0, rng: Optional[random.Random] = None):
        rng = rng or random.Random()
        self.width = float(width)
        self.speeds = [s * scale for s in self.SPEEDS]
        self.offsets = [rng.uniform(0.0, self.width) for _ in self.SPEEDS]

    def step(self, dt: float) -> None:
        if self.width > 0:
            self.offsets = [(o + s * dt) % self.width for o, s in zip(self.offsets, self.speeds)]
