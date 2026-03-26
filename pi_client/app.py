"""Raspberry Pi NFC POS display client.

Runs a local Flask web server that renders the kiosk UI.  A background daemon
thread continuously polls the NFC reader; when a card is detected it calls the
nanposweb server API to identify the user and transitions the shared state
machine so that the browser (running in kiosk mode) automatically shows the
correct screen.

State machine
-------------

::

    idle ──(card detected)──► identify ──(any user)──► user ──(buy)──► success ──► idle
                                         │             │                              ▲
                                         │             └──(admin clicks admin menu)──► admin ──(back)──► user
                                         │                                            └──(done/timeout)──► success ──► idle
                                         └──(error at any point)──► error ──(after 4 s)──► idle

Screens
-------

* **idle**    – "Karte antippen" splash; polls ``/api/state`` every 500 ms.
* **user**    – product grid for the identified user; admin users also see an
                "Admin-Menu" button that leads to the admin screen.
* **admin**   – list of users with balance-recharge controls; reached via the
                "Admin-Menu" button on the user screen.
* **success** – purchase confirmation; auto-redirects to idle after 3 s.
* **error**   – error message; auto-redirects to idle after 4 s.

Each Raspberry Pi runs its own instance and is completely independent.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
import time
from typing import Any, Optional, Union

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from api_client import APIError, NFCApiClient
from nfc_reader import NFCReader, build_reader

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    'SERVER_URL': 'http://localhost:5000',
    'API_KEY': '',
    'IDLE_TIMEOUT': 60,       # seconds before returning to idle after inactivity
    'NFC_POLL_INTERVAL': 0.3,  # seconds between NFC polls while idle
    'NFC_MOCK': False,
    'NFC_MOCK_UID': '04AABBCCDD',
    'NFC_MOCK_DELAY': 3.0,
    'NFC_PATH': 'usb',
    # Pre-defined top-up amounts shown as quick buttons in the admin panel (euros)
    'TOPUP_AMOUNTS': [10, 20, 30, 50],
}

# ---------------------------------------------------------------------------
# Shared application state (protected by _state_lock)
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    'mode': 'idle',       # idle | user | admin | success | error
    'card_uid': None,     # card UID of the currently active user
    'user_id': None,
    'user_name': None,
    'balance': None,      # in cents
    'is_admin': False,
    'favorites': [],      # [product_id, …]
    'products': [],       # [{id, name, price}, …]  (fetched once, cached)
    'users': [],          # [{id, name, balance}, …]  (admin only)
    'message': '',
    'last_activity': time.monotonic(),
    '_version': 0,        # incremented on every state change for polling
}


def _set_state(**kwargs: Any) -> None:
    """Update *_state* under the lock and bump the version counter."""
    with _state_lock:
        _state.update(kwargs)
        _state['last_activity'] = time.monotonic()
        _state['_version'] += 1


def _reset_to_idle() -> None:
    with _state_lock:
        _state.update({
            'mode': 'idle',
            'card_uid': None,
            'user_id': None,
            'user_name': None,
            'balance': None,
            'is_admin': False,
            'favorites': [],
            'products': [],
            'users': [],
            'message': '',
            'last_activity': time.monotonic(),
        })
        _state['_version'] += 1


# ---------------------------------------------------------------------------
# NFC polling thread
# ---------------------------------------------------------------------------


def _nfc_worker(reader: NFCReader, client: NFCApiClient, config: dict[str, Any]) -> None:
    """Background thread: poll NFC reader and handle card events."""
    poll_interval = float(config.get('NFC_POLL_INTERVAL', 0.3))
    idle_timeout = float(config.get('IDLE_TIMEOUT', 60))

    while True:
        # --- idle-timeout watchdog ---
        with _state_lock:
            mode = _state['mode']
            last_activity = _state['last_activity']

        if mode != 'idle' and (time.monotonic() - last_activity) > idle_timeout:
            logger.info('Idle timeout – resetting to idle')
            _reset_to_idle()
            time.sleep(poll_interval)
            continue

        # --- only scan when on idle screen ---
        if mode != 'idle':
            time.sleep(poll_interval)
            continue

        # --- try to read a card ---
        try:
            uid = reader.read_uid()
        except Exception:  # noqa: BLE001
            logger.exception('NFC read error')
            time.sleep(poll_interval)
            continue

        if not uid:
            time.sleep(poll_interval)
            continue

        logger.info('Card detected: %s', uid)
        _handle_card_scan(uid, client)


def _handle_card_scan(uid: str, client: NFCApiClient) -> None:
    """Identify the card and update the shared state accordingly."""
    try:
        user_info = client.identify(uid)
    except APIError as exc:
        if exc.status_code == 404:
            _set_state(mode='error', message=f'Karte nicht registriert.\nKarten-ID: {uid}')
        else:
            _set_state(mode='error', message=f'Serverfehler: {exc}')
        logger.warning('identify failed for uid=%s: %s', uid, exc)
        return

    is_admin: bool = user_info.get('is_admin', False)

    # Always show the product grid first – admins get an extra button to open
    # the admin panel from there.
    with _state_lock:
        cached_products = list(_state['products'])

    if not cached_products:
        try:
            cached_products = client.get_products()
        except APIError as exc:
            _set_state(mode='error', message=f'Produkte konnten nicht geladen werden: {exc}')
            logger.warning('get_products failed: %s', exc)
            return

    _set_state(
        mode='user',
        card_uid=uid,
        user_id=user_info['user_id'],
        user_name=user_info['name'],
        balance=user_info['balance'],
        is_admin=is_admin,
        favorites=user_info.get('favorites', []),
        products=cached_products,
        users=[],
    )
    logger.info(
        '%s screen for %s (balance: %d ct)',
        'Admin+Product' if is_admin else 'Product',
        user_info['name'],
        user_info['balance'],
    )


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)


def _read_config() -> dict[str, Any]:
    """Load config from ``config.py`` next to this file (if it exists)."""
    cfg = dict(_DEFAULT_CONFIG)
    spec = importlib.util.spec_from_file_location('pi_client_config', 'config.py')
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            for key in _DEFAULT_CONFIG:
                if hasattr(module, key):
                    cfg[key] = getattr(module, key)
        except Exception:  # noqa: BLE001
            logger.exception('Failed to load config.py – using defaults')
    return cfg


_config: dict[str, Any] = {}
_api_client: Optional[NFCApiClient] = None


@app.before_request
def _lazy_init() -> None:
    """Initialise config and client on first request (avoids circular init)."""
    global _config, _api_client  # noqa: PLW0603
    if _api_client is None:
        _config = _read_config()
        _api_client = NFCApiClient(_config['SERVER_URL'], _config['API_KEY'])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _fmt_currency(cents: Optional[int]) -> str:
    if cents is None:
        return '–'
    return f'{cents / 100:.2f} €'.replace('.', ',')


app.jinja_env.filters['fmt_currency'] = _fmt_currency  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route('/')
def index() -> Union[str, Response]:
    with _state_lock:
        mode = _state['mode']

    if mode == 'idle':
        return render_template('idle.html')
    if mode == 'user':
        with _state_lock:
            ctx = dict(_state)
        return render_template('user.html', **ctx)
    if mode == 'admin':
        with _state_lock:
            ctx = dict(_state)
        topup_amounts = _config.get('TOPUP_AMOUNTS', _DEFAULT_CONFIG['TOPUP_AMOUNTS'])
        return render_template('admin.html', topup_amounts=topup_amounts, **ctx)
    if mode in ('success', 'error'):
        with _state_lock:
            msg = _state['message']
        return render_template('result.html', mode=mode, message=msg)

    return redirect(url_for('index'))


@app.route('/api/state')
def api_state() -> Response:
    """Polling endpoint: returns current mode and version counter as JSON."""
    with _state_lock:
        return jsonify({'mode': _state['mode'], 'version': _state['_version']})


@app.route('/purchase', methods=['POST'])
def purchase() -> Response:
    """Handle product selection from the user screen."""
    product_id = request.form.get('product_id', type=int)
    if product_id is None:
        _set_state(mode='error', message='Kein Produkt ausgewählt.')
        return redirect(url_for('index'))

    with _state_lock:
        uid = _state.get('card_uid')
        user_name = _state.get('user_name', '')

    if not uid:
        _reset_to_idle()
        return redirect(url_for('index'))

    if _api_client is None:
        _reset_to_idle()
        return redirect(url_for('index'))

    try:
        result = _api_client.purchase(uid, product_id)
    except APIError as exc:
        _set_state(mode='error', message=f'Kauf fehlgeschlagen: {exc}')
        return redirect(url_for('index'))

    msg = (
        f'{user_name} hat {result["product_name"]} für '
        f'{_fmt_currency(result["amount"])} gekauft.\n'
        f'Neues Guthaben: {_fmt_currency(result["new_balance"])}'
    )
    _set_state(mode='success', message=msg)
    return redirect(url_for('index'))


@app.route('/admin/balance', methods=['POST'])
def admin_balance() -> Response:
    """Handle balance adjustment from the admin panel."""
    user_id = request.form.get('user_id', type=int)
    amount = request.form.get('amount', type=float)
    recharge = request.form.get('recharge', 'true').lower() == 'true'

    if user_id is None or amount is None or amount <= 0:
        _set_state(mode='error', message='Ungültige Eingabe.')
        return redirect(url_for('index'))

    with _state_lock:
        admin_uid = _state.get('card_uid')
        admin_name = _state.get('user_name', 'Admin')
        users = _state.get('users', [])

    user_name = next((u['name'] for u in users if u['id'] == user_id), f'Nutzer #{user_id}')

    if not admin_uid:
        _reset_to_idle()
        return redirect(url_for('index'))

    if _api_client is None:
        _reset_to_idle()
        return redirect(url_for('index'))

    try:
        result = _api_client.admin_balance(admin_uid, user_id, amount, recharge)
    except APIError as exc:
        _set_state(mode='error', message=f'Buchung fehlgeschlagen: {exc}')
        return redirect(url_for('index'))

    action = 'aufgeladen' if recharge else 'abgebucht'
    msg = (
        f'{user_name} wurden {_fmt_currency(int(amount * 100))} durch {admin_name} {action}.\n'
        f'Neues Guthaben: {_fmt_currency(result["new_balance"])}'
    )
    _set_state(mode='success', message=msg)
    return redirect(url_for('index'))


@app.route('/reset')
def reset() -> Response:
    """Manually reset to idle (e.g. user presses Cancel)."""
    _reset_to_idle()
    return redirect(url_for('index'))


@app.route('/admin')
def admin_panel() -> Union[str, Response]:
    """Open the admin panel for the currently identified admin user."""
    with _state_lock:
        is_admin = _state.get('is_admin', False)
        admin_uid = _state.get('card_uid')

    if not is_admin or not admin_uid:
        return redirect(url_for('index'))

    if _api_client is None:
        return redirect(url_for('index'))

    try:
        users = _api_client.get_users(admin_uid)
    except APIError as exc:
        _set_state(mode='error', message=f'Nutzerliste konnte nicht geladen werden: {exc}')
        logger.warning('get_users failed: %s', exc)
        return redirect(url_for('index'))

    _set_state(mode='admin', users=users)
    return redirect(url_for('index'))


@app.route('/admin/back')
def admin_back() -> Response:
    """Return from the admin panel to the product grid."""
    with _state_lock:
        is_admin = _state.get('is_admin', False)

    if is_admin:
        _set_state(mode='user')
    else:
        _reset_to_idle()
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cfg = _read_config()
    reader = build_reader(cfg)
    client = NFCApiClient(cfg['SERVER_URL'], cfg['API_KEY'])

    # Warm up product cache
    try:
        products = client.get_products()
        with _state_lock:
            _state['products'] = products
        logger.info('Loaded %d products from server', len(products))
    except APIError as exc:
        logger.warning('Could not pre-fetch products: %s', exc)

    # Start NFC polling thread
    nfc_thread = threading.Thread(
        target=_nfc_worker,
        args=(reader, client, cfg),
        daemon=True,
        name='nfc-worker',
    )
    nfc_thread.start()
    logger.info('NFC worker thread started')

    # Start Flask (blocks until Ctrl-C)
    app.run(
        host='127.0.0.1',
        port=int(cfg.get('PORT', 8080)),
        debug=False,
        use_reloader=False,
    )

    reader.close()


if __name__ == '__main__':
    main()
