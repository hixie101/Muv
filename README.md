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

`libxcb-cursor0` is required by Qt 6.5+ to load its X11 display plugin; without it Muv aborts at startup with a "Could not load the Qt platform plugin xcb" error.

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

Clock: the main clock shows 12-hour time with AM/PM and a smaller 24-hour time sits below it. Change them with `display.time_format` (default `"%I:%M %p"`) and `display.secondary_time_format` (default `"%H:%M"`; set it to `""` to hide the second clock). `display.date_format` controls the date line. These are standard Python `strftime` codes. The 24-hour clock is a quarter of the main clock's font size and sits right under it; `display.clock_gap` (default `4`, in pixels at 1080p) adds extra space between the two, so raise it if they look too cramped.

Wallpapers: drop images (`.jpg`, `.png`, `.bmp`, `.webp`) into a `wallpapers/` folder in the project, or enable `wallpaper.smb` to mirror a folder from a network share (SMB passwords can be supplied via `MUV_SMB_PASSWORD`). `config.json` is git-ignored so your keys and passwords are not committed.

Run it once by hand to check everything works (press **Esc** or **Q** to quit):

```bash
python main.py
```

Muv draws on the Pi's own desktop, so run this in a terminal on the Pi itself. If you are connected over SSH, point it at the desktop session instead, e.g. `DISPLAY=:0 python main.py` (X11), or on a Wayland desktop `XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0 QT_QPA_PLATFORM=wayland python main.py`. To test your config and network settings without a screen, use `QT_QPA_PLATFORM=offscreen python main.py`.

Problems found in your config (a missing API key, an invalid stop) are logged at startup.

### Step 7: Configure Automatic Boot to GUI (Autostart)
Current Raspberry Pi OS releases run the **labwc** Wayland desktop, which starts programs from `~/.config/labwc/autostart`. (A `~/.config/autostart/*.desktop` entry did not launch Muv on a trixie/labwc Pi.) The project includes `run_muv.sh`, which starts Muv from its own folder and logs to `~/muv.log`.

1. Make sure the Pi boots to the desktop (`sudo raspi-config` → System Options → Boot / Auto Login → **Desktop Autologin**).
2. Add the launcher to labwc's autostart. A user `autostart` file *replaces* the system one, so copy the system file first to keep the panel and desktop icons:
   ```bash
   chmod +x ~/Muv/run_muv.sh
   mkdir -p ~/.config/labwc
   [ -f ~/.config/labwc/autostart ] || cp /etc/xdg/labwc/autostart ~/.config/labwc/autostart
   echo "$HOME/Muv/run_muv.sh &" >> ~/.config/labwc/autostart
   ```
   If you cloned Muv somewhere other than `~/Muv`, change the path in the last line.
3. Reboot (`sudo reboot`). Muv should appear fullscreen on the monitor a few seconds after the desktop loads.

If it doesn't start, check `pgrep -af main.py` and read `~/muv.log` for the error. `run_muv.sh` also has commented-out lines for supplying the API key and SMB password as environment variables instead of keeping them in `config.json`.

*Older Raspberry Pi OS releases that use an X11 desktop (LXDE-pi) use a different autostart mechanism and are untested here.*

---

## Project Layout

```text
Muv/
├── main.py                  # Entry point: wires services to the window, handles shutdown
├── run_muv.sh               # Autostart launcher (logs to ~/muv.log)
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


---

## Updating Muv

To update Muv on your Pi to the latest version from GitHub, SSH in (or open a terminal on the Pi) and run:

```bash
cd ~/Muv && git pull && sudo reboot
```

This downloads the latest code and restarts the Pi so the new version starts automatically. Your `config.json` and `venv/` folder are not tracked by git, so your settings are kept.

- **New dependencies:** if an update changes `requirements.txt`, run `source venv/bin/activate && pip install -r requirements.txt` before rebooting.
- **If `git pull` refuses** because you edited files on the Pi, either undo your edits with `git checkout -- .` (this discards changes to tracked files) or save them aside with `git stash`, then run the update command again.
- **New settings:** new releases may add options to `config.example.json`. Your existing `config.json` keeps working because anything you don't set falls back to a default; copy across any new options you want to change.
- **Checking the result:** after the reboot, `tail -n 30 ~/muv.log` shows whether Muv started cleanly.
