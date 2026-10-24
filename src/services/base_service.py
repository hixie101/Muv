"""Base class for Muv's background data services."""

import logging
import threading
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from .errors import ConfigurationError, ServiceError

log = logging.getLogger(__name__)


class PollingService(QThread):
    """Runs ``poll()`` on its own thread every ``interval`` seconds.

    Subclasses implement:
      * ``poll()``    - do the (blocking) work and return a payload, or None to skip.
      * ``publish()`` - emit the payload on the subclass's own typed signal.

    Signals are emitted from the worker thread; Qt queues them onto the GUI thread
    because the receivers are widgets that live there. Failures never propagate:
    they are logged and reported through ``error(service_name, message)``.
    """

    # (service name, human-readable message)
    error = pyqtSignal(str, str)

    def __init__(self, service_name: str, interval: float, retry_interval: Optional[float] = None):
        super().__init__()
        self.service_name = service_name
        self.setObjectName(f"muv-{service_name}")
        self.interval = float(interval)
        self.retry_interval = float(retry_interval if retry_interval is not None else min(interval, 30))
        self._stop_event = threading.Event()

    @property
    def stopping(self) -> bool:
        return self._stop_event.is_set()

    def poll(self) -> Any:
        raise NotImplementedError

    def publish(self, payload: Any) -> None:
        raise NotImplementedError

    def _report(self, message: str) -> None:
        self.error.emit(self.service_name, message)

    def run(self) -> None:
        log.info("%s service started", self.service_name)
        while not self._stop_event.is_set():
            delay = self.interval
            try:
                payload = self.poll()
            except ConfigurationError as exc:
                # Retrying will not fix a bad setting, so wait a full interval.
                log.error("%s: %s", self.service_name, exc)
                self._report(str(exc))
            except ServiceError as exc:
                log.warning("%s: %s", self.service_name, exc)
                self._report(str(exc))
                delay = self.retry_interval
            except Exception:  # a bug; keep the signage running
                log.exception("%s: unexpected error while polling", self.service_name)
                self._report("unexpected error (see log)")
                delay = self.retry_interval
            else:
                if payload is not None and not self.stopping:
                    self.publish(payload)
            # Event.wait returns immediately once stop() is called.
            self._stop_event.wait(delay)
        log.info("%s service stopped", self.service_name)

    def request_stop(self) -> None:
        """Signal the thread to finish without waiting (lets several stop in parallel)."""
        self._stop_event.set()

    def stop(self, timeout_ms: int = 15000) -> None:
        """Ask the thread to finish and wait for it."""
        self.request_stop()
        if self.isRunning() and not self.wait(timeout_ms):
            log.warning("%s service did not stop in time; terminating", self.service_name)
            self.terminate()
            self.wait(1000)
