# Pi Client – NFC Kiosk Terminal

This directory contains a standalone Python application that runs on a
Raspberry Pi.  It reads NFC card UIDs with a connected reader, talks to the
central **nanposweb** server via its REST API, and renders a kiosk UI in a
local browser window.

Each Pi is fully independent – multiple terminals can be used simultaneously
in different locations without interfering with each other.

---

## Architecture overview

```
┌──────────────────────── Raspberry Pi ─────────────────────────┐
│                                                                │
│  NFC reader (USB / SPI)                                        │
│       │                                                        │
│  nfc_reader.py  ──read_uid()──►  app.py  ◄──── browser        │
│                                    │        (kiosk mode)       │
│                              api_client.py                     │
│                                    │                           │
└────────────────────────────────────┼───────────────────────────┘
                                     │  HTTPS / HTTP
                              ┌──────▼──────┐
                              │  nanposweb  │
                              │  server     │
                              │  /api/nfc/* │
                              └─────────────┘
```

`app.py` runs two things concurrently:

1. A **background thread** that continuously polls the NFC reader.  When a
   card is detected it calls `/api/nfc/identify`, updates the in-memory state
   machine, and optionally fetches extra data (product list or user list).

2. A **local Flask web server** (default port `8080`) that serves the kiosk
   UI.  The browser polls `/api/state` every 500 ms and navigates to the
   correct screen whenever the state changes.

---

## Screens

| State | Screen | Description |
|-------|--------|-------------|
| `idle` | **Idle** | "Karte antippen" – waits for a card scan |
| `user` | **Product grid** | Shows all visible drinks with prices for the identified user |
| `admin` | **Admin panel** | Lists all users with balances; admin can top up or charge |
| `success` | **Success** | Confirmation message; auto-returns to idle after 3 s |
| `error` | **Error** | Error message; auto-returns to idle after 5 s |

---

## Requirements

- Raspberry Pi (any model with USB or SPI/I2C support)
- Supported NFC reader, e.g.:
  - **ACR122U** (USB) – plug-and-play on Raspberry Pi OS
  - **PN532** breakout board via SPI or UART
- Python 3.11+
- A running **nanposweb** server with `NFC_API_KEY` configured

---

## Installation

```bash
# 1. Install system packages (ACR122U / libnfc)
sudo apt update && sudo apt install -y libnfc-dev libusb-dev

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. For real NFC hardware also install nfcpy
pip install nfcpy

# 5. Copy and edit the configuration
cp config.py.example config.py
nano config.py        # set SERVER_URL and API_KEY at minimum
```

### Server-side configuration

In the nanposweb server's `instance/config.py`, add:

```python
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
NFC_API_KEY = 'your-long-random-secret-here'
```

The same value must be set as `API_KEY` in the Pi's `config.py`.

---

## Registering NFC cards

Cards are registered in the nanposweb web interface:

1. Log in as the user (or as an admin).
2. Go to **Account → Change Card**.
3. Enter the card's UID (the hex string printed by `nfc-list` or visible in
   the Pi client logs).
4. Save.

The UID is stored as a SHA-256 hash – the plaintext UID is never kept on the
server.

---

## Running

```bash
source .venv/bin/activate
python app.py
```

Open a browser to `http://localhost:8080` (or the configured `PORT`).

For kiosk mode on Raspberry Pi OS with a touchscreen, add this to
`~/.config/lxsession/LXDE-pi/autostart`:

```
@chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8080
```

---

## Mock mode (testing without hardware)

Set `NFC_MOCK = True` in `config.py`.  The reader will simulate a card scan
every `NFC_MOCK_DELAY` seconds using the UID in `NFC_MOCK_UID`.  Make sure
that UID is registered in the server database.

---

## Running multiple Pis

Each Pi runs its own independent instance of `app.py` pointing at the same
central nanposweb server.  No additional configuration is needed – they simply
make independent HTTP calls to the shared server.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `nfcpy` can't find the reader | Check USB connection; run `nfc-list` to verify the reader is detected by libnfc |
| "NFC API not configured on this server" (503) | Set `NFC_API_KEY` in the server's `instance/config.py` and restart |
| "Unauthorized" (401) | Check that `API_KEY` in `config.py` matches `NFC_API_KEY` on the server |
| "Card not registered" (404) | Register the card UID via **Account → Change Card** in the web UI |
| Screen stays on idle after card scan | Check server logs and Pi logs for error messages |
