# Muv

**Muv** is a lightweight, Python-powered digital signage application designed for the Raspberry Pi. It turns an HDMI-connected monitor into a clean, real-time display showing a live clock, current weather and forecast, and live Hong Kong bus arrival times (KMB and Citybus), over a rotating wallpaper.

---

## Features
- **Real-time data:** Weather from OpenWeatherMap and bus ETAs from the official KMB and Citybus open-data APIs, refreshed on a timer.
- **Background threads:** Each data source polls on its own thread with request timeouts, so a slow or dead network never freezes the clock or the animations. If a refresh fails, the last good data stays on screen and a small status line explains what went wrong.
- **Rotating wallpapers:** Cross-fades between images from a local folder or an SMB/CIFS network share. The fade length is configurable (`display.fade_ms`; set `0` to disable on slower boards).
- **Configurable:** Everything is set in `config.json`; secrets can come from environment variables instead.

---

## Installation & Setup Guide

Follow this guide to provision, configure, and launch **Muv** on a fresh Raspberry Pi.

### Step 1: Flash the Operating System
1. Download and open the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Choose your hardware (e.g., **Raspberry Pi 3**).
3. For the Operating System, select **Raspberry Pi OS (64-bit)**.
   - *Choose the standard Desktop version: Muv is a GUI application and needs a display server.*
4. Click the gear icon (**Edit Settings**) to configure headless deployment variables before flashing:
   - Enable **SSH** (set a username and password).
   - Configure your **Wi-Fi SSID** and password.
   - Set your **Locale settings** (the timezone decides what the clock shows).
5. Click **Write** to flash your microSD card. Insert the card into your Pi and power it on.

### Step 2: Connect and Update the System
Connect to the Pi over SSH (replace `username` and `raspberrypi.local` with your own):

```bash
ssh username@raspberrypi.local
```

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 3: Install System Dependencies
```bash
sudo apt install git python3-pip python3-venv python3-pyqt6 libxcb-cursor0 -y
```

### Step 4: Clone the Project and Create a Virtual Environment
```bash
git clone https://github.com/hixie101/Muv.git
cd Muv

# --system-site-packages lets the venv see the apt-installed PyQt6
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

### Step 5: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 6: Configure Muv
```bash
cp config.example.json config.json
nano config.json
```

At minimum, set:

- **`weather.api_key`**: a free key from [OpenWeatherMap](https://openweathermap.org/api). Alternatively export `MUV_OPENWEATHER_API_KEY` and leave the file value empty. New keys can take a while to activate.
- **`transit.stops`**: the bus stops to show. Each entry needs:
  - `operator`: `"KMB"` or `"CTB"`
  - `stop_id`: the operator's stop ID
  - `route`: the route number, e.g. `"1A"`
  - `label` (optional): text shown beside the route
  - `service_type` (optional, KMB only): defaults to `1`

  Entries still containing `REPLACE_WITH_STOP_ID` are ignored. You can look up stop IDs in the operators' open data: for KMB, `https://data.etabus.gov.hk/v1/transport/kmb/stop` lists every stop; for Citybus, `https://rt.data.gov.hk/v2/transport/citybus/route-stop/CTB/<route>/outbound` (or `inbound`) lists a route's stops. Details are on [data.gov.hk](https://data.gov.hk).

Wallpapers: drop images (`.jpg`, `.png`, `.bmp`, `.webp`) into a `wallpapers/` folder in the project, or enable `wallpaper.smb` to mirror a folder from a network share (SMB passwords can be supplied via `MUV_SMB_PASSWORD`). `config.json` is git-ignored so your keys and passwords are not committed.

Run it once by hand to check everything works (press **Esc** or **Q** to quit):

```bash
python main.py
```

Problems found in your config (a missing API key, an invalid stop) are logged at startup.

### Step 7: Configure Automatic Boot to GUI (Autostart)
To launch the dashboard whenever the Pi boots to the desktop:

1. Create the autostart directory:
   ```bash
   mkdir -p ~/.config/autostart
   ```
2. Create a desktop entry:
   ```bash
   nano ~/.config/autostart/muv_dashboard.desktop
   ```
3. Paste the following (adjust the paths to your username and install location):
   ```text
   [Desktop Entry]
   Type=Application
   Name=Muv Dashboard
   Path=/home/YOUR_USERNAME/Muv
   Exec=/home/YOUR_USERNAME/Muv/venv/bin/python /home/YOUR_USERNAME/Muv/main.py
   ```
4. Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

*Autostart behaviour depends on your Raspberry Pi OS version and whether it runs X11 or Wayland. If the entry doesn't launch Muv, check the Raspberry Pi documentation for your desktop session.*

---

## Project Layout

```text
Muv/
├── main.py                  # Entry point: wires services to the window, handles shutdown
├── config.example.json      # Copy to config.json and edit
├── requirements.txt
├── LICENSE
├── README.md
├── src/
│   ├── services/
│   │   ├── base_service.py       # PollingService: background thread + error handling
│   │   ├── weather_service.py    # OpenWeatherMap poller
│   │   ├── transport_service.py  # KMB / Citybus API client (no Qt, easy to test)
│   │   ├── bus_service.py        # Polls transport_service on a background thread
│   │   ├── smb_service.py        # Wallpaper rotation, optional SMB mirroring
│   │   └── errors.py
│   ├── ui/
│   │   └── app_window.py         # Window, wallpaper cross-fade, clock/weather/bus panels
│   └── utils/
│       └── config_manager.py     # Loads and validates config.json
└── tests/                        # python3 -m unittest discover -s tests -t .
```

---

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license.

### Quick Summary
- **Home/Personal Use:** You are free to download, modify, use, and run this application in your private home environment.
- **Commercial Use:** You **cannot** use this material for commercial purposes or financial gain. This includes deploying it in commercial office buildings or retail lobbies, embedding it in commercial hardware, or selling derivative configurations to clients.

*For the full legal terms, read the `LICENSE` file in this repository or visit the [Creative Commons legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode).*

### Commercial Exemptions
If you want to deploy this software in a commercial environment, please open an issue or contact the repository owner to negotiate a commercial-use waiver.

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
