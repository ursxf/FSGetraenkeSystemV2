#!/bin/bash

# Exit on any error
set -e

# Ensure we're not running as root, but can use sudo
if [ "$EUID" -eq 0 ]; then
  echo "Please run as your normal user (e.g. pi), not as root."
  exit 1
fi

USER_HOME=$HOME
CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "  Installing system dependencies...     "
echo "========================================"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    wayfire wlr-randr chromium \
    libnfc-dev libusb-dev python3-venv python3-pip git \
    liblgpio-dev python3-dev swig

echo "Adding user to necessary hardware groups..."
sudo usermod -a -G spi,gpio,video,render,input $USER

echo "========================================"
echo "  Setting up Python environment...      "
echo "========================================"
cd "$CLIENT_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
pip install nfcpy

if [ ! -f "config.py" ]; then
    cp config.py.example config.py
    echo "Created config.py from template."
fi

echo "========================================"
echo "  Configuring Systemd service...        "
echo "========================================"
cat << EOF | sudo tee /etc/systemd/system/nanpos-client.service > /dev/null
[Unit]
Description=Nanpos Pi Client
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$CLIENT_DIR
ExecStart=$CLIENT_DIR/.venv/bin/python $CLIENT_DIR/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable nanpos-client.service

echo "========================================"
echo "  Configuring Kiosk Mode (Wayfire)...   "
echo "========================================"
mkdir -p "$USER_HOME/.config"
cat << EOF > "$USER_HOME/.config/wayfire.ini"
[core]
plugins = autostart

[autostart]
# Wait a few seconds to ensure the python app is up and running
chromium = sh -c 'sleep 5 && chromium --noerrdialogs --disable-infobars --kiosk http://localhost:8080'
EOF
sudo chown -R $USER:$USER "$USER_HOME/.config"

echo "Configuring Wayland to start on login..."
# create .bash_profile to start Wayfire on the first console
if ! grep -q "wayfire" "$USER_HOME/.bash_profile" 2>/dev/null; then
cat << 'EOF' >> "$USER_HOME/.bash_profile"

# Start Wayfire automatically on tty1
if [[ -z \$WAYLAND_DISPLAY && \$XDG_VTNR -eq 1 ]]; then
  exec wayfire
fi
EOF
fi

echo "========================================"
echo "  Configuring Raspberry Pi settings...  "
echo "========================================"
echo "Enabling console autologin..."
sudo raspi-config nonint do_boot_behaviour B2

echo "Disabling screen blanking in raspi-config..."
sudo raspi-config nonint do_blanking 1

echo "========================================"
echo "  Setup Complete!                       "
echo "========================================"
echo ""
echo "Please configure your API Key and Server URL:"
echo "  nano $CLIENT_DIR/config.py"
echo ""
echo "After configuring, you can reboot the Pi to start the Kiosk:"
echo "  sudo reboot"
echo "========================================"
