"""NFC reader abstraction for the Raspberry Pi POS client.

Two implementations are provided:

* ``RealNFCReader``  – uses *nfcpy* to talk to a physical NFC reader
  (e.g. ACR122U via USB, PN532 via SPI/UART/I2C).
* ``MockNFCReader``  – returns a configurable UID; useful for development
  without real hardware.

Usage::

    reader = build_reader(config)
    uid = reader.read_uid()   # blocks until a card is detected, returns hex UID

The returned UID is an upper-case hex string without separators, e.g.
``"04AABBCCDD"``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class NFCReader(ABC):
    """Abstract base class for NFC readers."""

    @abstractmethod
    def read_uid(self) -> Optional[str]:
        """Block until a card is presented and return its UID as a hex string.

        Returns ``None`` if the read was interrupted or timed out.
        """

    def close(self) -> None:  # noqa: B027
        """Release hardware resources (optional)."""


# ---------------------------------------------------------------------------
# Real hardware reader (nfcpy)
# ---------------------------------------------------------------------------


class RealNFCReader(NFCReader):
    """NFC reader backed by nfcpy.

    *path* is the nfcpy device path, e.g. ``"usb"`` (first USB reader),
    ``"usb:072f:2200"`` (specific VID:PID), or ``"tty:S0:pn532"`` for a
    serial PN532.  See the nfcpy documentation for the full syntax.
    """

    def __init__(self, path: str = 'usb') -> None:
        try:
            import nfc  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                'nfcpy is required for real NFC hardware. '
                'Install it with: pip install nfcpy'
            ) from exc

        self._nfc = nfc
        self._path = path
        self._clf = nfc.ContactlessFrontend(path)
        logger.info('NFC frontend opened: %s', path)

    def read_uid(self) -> Optional[str]:  # noqa: ANN001
        uid_holder: list[str] = []

        def _on_connect(tag: object) -> bool:  # noqa: ANN001
            uid_bytes: bytes = getattr(tag, 'identifier', b'')
            uid_holder.append(uid_bytes.hex().upper())
            return False  # release the tag immediately

        self._clf.connect(rdwr={'on-connect': _on_connect})
        return uid_holder[0] if uid_holder else None

    def close(self) -> None:
        self._clf.close()
        logger.info('NFC frontend closed')


# ---------------------------------------------------------------------------
# Mock reader (testing / development)
# ---------------------------------------------------------------------------


class MockNFCReader(NFCReader):
    """Simulates an NFC reader for development without hardware.

    It cycles through *uids* (or just the single *uid*) with a configurable
    delay between presentations.  Set *delay* to 0 to return immediately.
    """

    def __init__(self, uid: str = '04AABBCCDD', delay: float = 2.0) -> None:
        self._uid = uid
        self._delay = delay

    def read_uid(self) -> Optional[str]:
        if self._delay > 0:
            time.sleep(self._delay)
        return self._uid.upper()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_reader(config: dict) -> NFCReader:  # type: ignore[type-arg]
    """Construct the appropriate NFCReader from *config*.

    Config keys (all optional):

    ``NFC_MOCK``
        If ``True``, a :class:`MockNFCReader` is used regardless of hardware.
    ``NFC_MOCK_UID``
        UID returned by the mock reader (default: ``"04AABBCCDD"``).
    ``NFC_MOCK_DELAY``
        Seconds between mock card events (default: ``2.0``).
    ``NFC_PATH``
        nfcpy device path (default: ``"usb"``).
    """
    if config.get('NFC_MOCK', False):
        uid = config.get('NFC_MOCK_UID', '04AABBCCDD')
        delay = float(config.get('NFC_MOCK_DELAY', 2.0))
        logger.info('Using mock NFC reader (uid=%s, delay=%.1fs)', uid, delay)
        return MockNFCReader(uid=uid, delay=delay)

    path = config.get('NFC_PATH', 'usb')
    logger.info('Using real NFC reader (path=%s)', path)
    return RealNFCReader(path=path)
