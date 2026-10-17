# Muv


**Muv** is a lightweight, Python-powered smart dashboard application designed specifically for the Raspberry Pi. It transforms an HDMI-connected monitor into a clean, real-time household display showing a live clock, dynamic weather updates, and live public transit schedules via external APIs. 

Optimized to run smoothly on hardware like the Raspberry Pi 3 Model B or above, the UI supports fluid background wallpaper shifts and crisp animations without stalling background data synchronization.

---

## Features
- **Real-Time Data Ingestion:** Fetches weather updates and live bus timetables via external JSON APIs.
- **Asynchronous Processing:** Built using background threads so API networking delays never freeze visual display animations.
- **Dynamic UI:** Smoothly changes background wallpapers and displays fluid transitions.
- **Developer Optimized:** Specifically tailored for headless operation and remote deployment workflows.

---

## Installation & Setup Guide

Follow this step-by-step guide to provision, configure, and launch **Muv** starting from a completely fresh, bare Raspberry Pi.

### Step 1: Flash the Operating System
1. Download and open the [Raspberry Pi Imager](https://www.raspberry ://pi.com).
2. Choose your hardware (e.g., **Raspberry Pi 3**).
3. For the Operating System, select **Raspberry Pi OS (64-bit)**. 
   - *Note: Choose the standard Desktop version if you plan to launch the GUI directly to an HDMI monitor via the system's X11/Wayland display server.*
4. Click the gear icon (**Edit Settings**) to configure headless deployment variables before flashing:
   - Enable **SSH** (Set a username and password).
   - Configure your **Wi-Fi SSID** and password.
   - Set your **Locale settings** (Timezone is critical for the dashboard clock).
5. Click **Write** to flash your microSD card. Insert the card into your Pi and power it on.

### Step 2: Connect and Update the System
Open a terminal on your development computer and connect to the Pi remotely via SSH (replace `username` and `raspberrypi.local` with your chosen configuration):

```bash
ssh username@raspberrypi.local
```

Once connected, run system updates to ensure all package repositories are current:

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 3: Install Core System Dependencies
Your Python application requires system-level graphics, image rendering libraries, and git. Install them by running:

```bash
sudo apt install git python3-pip python3-venv python3-pygame -y
```

### Step 4: Clone the Project and Create a Virtual Environment
Navigate to your desired directory, clone this repository, and set up an isolated Python virtual environment to manage dependencies securely:

```bash
# Clone the repository
git clone https://github.com
cd Muv

# Create a virtual environment including system packages for Pygame access
python3 -m venv --system-site-packages venv

# Activate the virtual environment
source venv/bin/activate
```

### Step 5: Install Python Dependencies
Install required packages, such as `requests` for fetching api data:

```bash
pip install requests
```

### Step 6: Configure Automatic Boot to GUI (Autostart)
To ensure the dashboard launches instantly whenever the Raspberry Pi boots up, configure a local autostart script:

1. Create the local autostart directory configuration path:
   ```bash
   mkdir -p ~/.config/autostart
   ```
2. Create and edit a new desktop initialization entry:
   ```bash
   nano ~/.config/autostart/muv_dashboard.desktop
   ```
3. Paste the following configuration inside the file (adjust the file path to point to your exact `main.py` entry point):
   ```text
   [Desktop Entry]
   Type=Application
   Name=Muv Dashboard
   Exec=/home/YOUR_USERNAME/Muv/venv/bin/python /home/YOUR_USERNAME/Muv/main.py
   X-GNOME-Autostart-enabled=true
   ```
4. Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## File Architecture Blueprint

To ensure animations stay buttery-smooth at 60 FPS, the codebase is structured to keep networking separate from rendering. Ensure your files adhere to this model:

```text
Muv/
├── main.py              # Main UI rendering loop (Pygame/Tkinter), animation handlers, wallpaper managers.
├── LICENSE              # Licensing constraints document.
├── README.md            # Installation and operational overview.
└── src/
    └── services/
        ├── __init__.py
        ├── weather_services.py   # Asynchronous background worker for weather API payload retrieval.
        └── transit_services.py   # Asynchronous background worker for bus timetable API processing.
```

---

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license.

### Quick Summary
- **Home/Personal Use:** You are completely free to download, modify, use, and run this application inside your private home environment for free.
- **Commercial Use:** You **cannot** use this material for commercial purposes or financial gain. This includes deploying it in commercial office buildings, retail lobbies, embedding it into commercial hardware enclosures, or selling derivative configurations to clients.

*To review the full legal terms, read the `LICENSE` file included in this repository or visit the [Creative Commons Legal Code](https://creativecommons.orglegalcode).*

### Commercial Exemptions
If you are looking to deploy this dashboard software in a commercial environment or require enterprise integrations, please open an inquiry or contact the repository owner directly to negotiate a custom, commercial-use waiver.
[![License: CC BY-NC 4.0](https://shields.io)](https://creativecommons.org)
