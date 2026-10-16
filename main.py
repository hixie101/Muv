"""
Muv - Raspberry Pi Digital Signage System
Main entry point for the Muv application.
"""
import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from src.ui.app_window import AppWindow
from src.services.weather_service import WeatherService
from src.services.bus_service import BusService
from src.services.smb_service import SMBService
from src.utils.config_manager import ConfigManager

class MuvApp:
    def __init__(self):
        self.config = ConfigManager()
        self.weather_service = WeatherService()
        self.bus_service = BusService()
        self.smb_service = SMBService()
        self.app = QApplication(sys.argv)
        self.window = AppWindow(self.config)
        self.timer = QTimer()
        
    def setup_connections(self):
        """Connect services to UI updates."""
        self.weather_service.data_fetched.connect(self.window.update_weather)
        self.bus_service.data_fetched.connect(self.window.update_bus)
        self.smb_service.image_rotated.connect(self.window.update_background)
        
    def start_services(self):
        """Start all background services."""
        self.weather_service.start()
        self.bus_service.start()
        self.smb_service.start()
        
    def run(self):
        """Run the Muv application."""
        self.setup_connections()
        self.window.showFullScreen()
        self.start_services()
        
        # Start background timer for UI updates
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)  # Update every second
        
        return self.app.exec()
        
    def update_ui(self):
        """Update UI elements."""
        self.window.update_time()
        
    def shutdown(self):
        """Shutdown all services."""
        self.weather_service.stop()
        self.bus_service.stop()
        self.smb_service.stop()
        self.timer.stop()
        self.window.close()

if __name__ == "__main__":
    app = MuvApp()
    exit_code = app.run()
    app.shutdown()
    sys.exit(exit_code)
