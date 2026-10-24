"""Wallpaper service for Muv.

Rotates through the images in a folder. With ``wallpaper.smb.enabled`` it first
mirrors images from an SMB/CIFS share into a local cache folder (needs ``pysmb``);
otherwise it just uses ``wallpaper.local_dir``. Rotation keeps working from the
cache if the share is unreachable.
"""

import logging
import posixpath
import random
import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal

from .base_service import PollingService
from .errors import ConfigurationError, ServiceError

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_FILE_BYTES = 25 * 1024 * 1024  # skip huge files; they would crawl on a Pi


class SMBService(PollingService):
    """Emits ``image_rotated(path)`` every ``wallpaper.rotate_seconds``."""

    image_rotated = pyqtSignal(str)

    def __init__(self, config):
        settings = config.section("wallpaper")
        rotate = settings["rotate_seconds"]
        super().__init__("wallpaper", rotate, retry_interval=min(rotate, 30))
        self.smb = settings["smb"]
        self.local_dir = config.resolve_path(settings["local_dir"])
        self.cache_dir = config.resolve_path(settings["cache_dir"])
        self._last_sync: Optional[float] = None
        self._queue: List[Path] = []
        self._last_shown: Optional[Path] = None

    @property
    def image_dir(self) -> Path:
        return self.cache_dir if self.smb.get("enabled") else self.local_dir

    # ---- rotation ------------------------------------------------------
    def poll(self) -> Optional[str]:
        if self.smb.get("enabled"):
            self._sync_if_due()
        path = self._next_image()
        return str(path) if path else None

    def publish(self, payload: str) -> None:
        self.image_rotated.emit(payload)

    def _list_images(self) -> List[Path]:
        try:
            return sorted(
                p for p in self.image_dir.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
        except OSError:
            return []

    def _next_image(self) -> Optional[Path]:
        """Shuffled round-robin: every image is shown once before any repeats."""
        self._queue = [p for p in self._queue if p.is_file()]
        if not self._queue:
            self._queue = self._list_images()
            if not self._queue:
                return None
            random.shuffle(self._queue)
            if len(self._queue) > 1 and self._queue[0] == self._last_shown:
                self._queue.append(self._queue.pop(0))  # no repeat across the reshuffle
        self._last_shown = self._queue.pop(0)
        return self._last_shown

    # ---- SMB mirroring -------------------------------------------------
    def _sync_if_due(self) -> None:
        now = time.monotonic()
        interval = self.smb.get("sync_seconds", 900)
        if self._last_sync is not None and now - self._last_sync < interval:
            return
        self._last_sync = now  # also throttles retries after a failure
        try:
            self._sync()
        except ServiceError as exc:
            log.warning("wallpaper: sync failed: %s", exc)
            self._report(str(exc))
        except Exception as exc:
            log.warning("wallpaper: sync failed: %s", exc, exc_info=True)
            self._report("could not sync wallpapers from the SMB share")

    def _sync(self) -> None:
        try:
            from smb.SMBConnection import SMBConnection
        except ImportError as exc:
            raise ConfigurationError("SMB wallpapers need pysmb (pip install pysmb)") from exc

        cfg = self.smb
        if not cfg.get("server") or not cfg.get("share"):
            raise ConfigurationError("wallpaper.smb.server and wallpaper.smb.share must be set")

        port = int(cfg.get("port", 445))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # pysmb wants the server's NetBIOS name as remote_name; the hostname usually works over 445.
        conn = SMBConnection(
            cfg.get("username", ""), cfg.get("password", ""), "muv", cfg["server"],
            use_ntlm_v2=True, is_direct_tcp=(port == 445),
        )
        try:
            if not conn.connect(cfg["server"], port, timeout=10):
                raise ServiceError("SMB login failed (check username and password)")
            remote_dir = cfg.get("path") or "/"
            entries = conn.listPath(cfg["share"], remote_dir)
            wanted = [
                e for e in entries
                if not e.isDirectory
                and Path(e.filename).suffix.lower() in IMAGE_EXTENSIONS
                and e.file_size <= MAX_FILE_BYTES
            ][: int(cfg.get("max_files", 50))]

            keep = set()
            for entry in wanted:
                if self.stopping:
                    return
                name = Path(entry.filename).name  # never trust a remote name as a path
                keep.add(name)
                dest = self.cache_dir / name
                if dest.exists() and dest.stat().st_size == entry.file_size:
                    continue
                partial = dest.with_name(dest.name + ".part")
                with partial.open("wb") as handle:
                    conn.retrieveFile(cfg["share"], posixpath.join(remote_dir, entry.filename), handle)
                partial.replace(dest)
                log.info("wallpaper: downloaded %s", name)

            for stale in self._list_images():
                if stale.name not in keep:
                    stale.unlink(missing_ok=True)
        finally:
            conn.close()
