"""
Muv - Raspberry Pi Digital Signage System
Main entry point for the Muv application.
"""
import logging
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.services.bus_service import BusService
from src.services.smb_service import SMBService
from src.services.weather_service import WeatherService
from src.ui.app_window import AppWindow
from src.utils.config_manager import ConfigError, ConfigManager

log = logging.getLogger("muv")


class MuvApp:
    def __init__(self, config: ConfigManager):
        self.config = config
        # QApplication first: everything Qt-related is created after it.
        self.app = QApplication(sys.argv)
        self.window = AppWindow(config)
        self.weather_service = WeatherService(config)
        self.bus_service = BusService(config)
        self.smb_service = SMBService(config)
        self.timer = QTimer()
        self._shut_down = False
        self.app.aboutToQuit.connect(self.shutdown)

    def setup_connections(self):
        """Connect services to UI updates.

        Connect to bound methods of the window (not lambdas) so Qt queues each
        signal onto the GUI thread; the services emit from worker threads.
        """
        self.weather_service.data_fetched.connect(self.window.update_weather)
        self.weather_service.error.connect(self.window.set_error)
        self.bus_service.data_fetched.connect(self.window.update_bus)
        self.bus_service.error.connect(self.window.set_error)
        self.smb_service.image_rotated.connect(self.window.update_background)
        # Wallpaper problems are cosmetic; they are logged but not shown on screen.

    def start_services(self):
        """Start all background services."""
        self.weather_service.start()
        self.bus_service.start()
        self.smb_service.start()

    def run(self):
        """Run the Muv application."""
        self.setup_connections()
        self.window.present()
        self.start_services()

        # Ctrl+C / SIGTERM (e.g. systemd stop) quit cleanly. Python only runs signal
        # handlers when the interpreter gets control, which this frequent timer ensures.
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.timer.timeout.connect(self.update_ui)
        self.timer.start(250)  # the clock text only changes (and repaints) once a second
        return self.app.exec()

    def _handle_signal(self, signum, _frame):
        log.info("Received signal %s; shutting down", signum)
        self.app.quit()

    def update_ui(self):
        """Update UI elements."""
        self.window.update_time()

    def shutdown(self):
        """Stop all services (safe to call more than once)."""
        if self._shut_down:
            return
        self._shut_down = True
        self.timer.stop()
        services = (self.weather_service, self.bus_service, self.smb_service)
        for service in services:
            service.request_stop()  # signal all first so they wind down in parallel
        for service in services:
            service.stop()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = ConfigManager()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    level = getattr(logging, str(config.get("log_level", "INFO")).upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    for warning in config.warnings():
        log.warning("config: %s", warning)

    muv = MuvApp(config)
    exit_code = muv.run()
    muv.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
