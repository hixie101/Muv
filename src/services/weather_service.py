"""
Weather Service for Muv
Handles fetching and caching weather data from OpenWeatherMap API.
"""

import threading
import queue
import requests
import time
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPixmap

class WeatherService(QObject):
    data_fetched = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.api_key = "YOUR_OPENWEATHERMAP_API_KEY"
        self.city = "Hong Kong"
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.current_weather = None
        self.forecast_data = None
        self.is_running = False
        self.timer = None
        
    def start(self):
        """Start the weather service."""
        self.is_running = True
        self.fetch_weather()
        
    def stop(self):
        """Stop the weather service."""
        self.is_running = False
        
    def fetch_weather(self):
        """Fetch current weather and forecast data."""
        try:
            # Fetch current weather
            current_url = f"{self.base_url}/weather"
            current_params = {
                "q": self.city,
                "appid": self.api_key,
                "units": "metric"
            }
            current_response = requests.get(current_url, params=current_params)
            if current_response.status_code == 200:
                self.current_weather = current_response.json()
                
            # Fetch forecast data
            forecast_url = f"{self.base_url}/forecast"
            forecast_params = {
                "q": self.city,
                "appid": self.api_key,
                "units": "metric"
            }
            forecast_response = requests.get(forecast_url, params=forecast_params)
            if forecast_response.status_code == 200:
                self.forecast_data = forecast_response.json()
                
            # Emit data
            self.data_fetched.emit({
                "current": self.current_weather,
                "forecast": self.forecast_data
            })
            
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            
    def get_weather_icon_path(self, icon_code):
        """Get the path to the weather icon."""
        return f"/assets/icons/weather/{icon_code}.png"
        
    def get_weather_animation(self, weather_condition):
        """Get animation type for current weather."""
        animations = {
            "Clear": "sun",
            "Clouds": "cloud",
            "Rain": "rain",
            "Drizzle": "drizzle",
            "Thunderstorm": "thunder",
            "Snow": "snow",
            "Mist": "mist"
        }
        return animations.get(weather_condition, "sun")
