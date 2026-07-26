"""Display management via PIR sensor and X11 DPMS."""

import logging
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DisplayManager:
    """Manages the Pi display power state using DPMS and a PIR sensor."""

    def __init__(self, pir_pin: Optional[int], timeout: int):
        self.pir_pin = pir_pin
        self.timeout = timeout
        self.last_activity = time.monotonic()
        self.is_on = True
        self.lock = threading.Lock()
        self.pir = None

        if self.pir_pin is not None:
            try:
                from gpiozero import MotionSensor
                # Initialize PIR sensor
                self.pir = MotionSensor(self.pir_pin)
                # When motion is detected, trigger the wake function
                self.pir.when_motion = self.wake
                logger.info('PIR sensor initialized on GPIO %s (timeout: %ss)', self.pir_pin, self.timeout)
            except ImportError:
                logger.warning('gpiozero not installed – PIR sensor disabled.')
            except Exception as e:
                logger.error('Failed to initialize PIR sensor on GPIO %s: %s', self.pir_pin, e)
        else:
            logger.info('PIR sensor disabled via config (PIR_PIN=None).')

    def wake(self) -> None:
        """Wake up the display (or keep it awake) and reset the timeout counter."""
        with self.lock:
            self.last_activity = time.monotonic()
            if not self.is_on:
                self._turn_on()
                self.is_on = True

    def _turn_on(self) -> None:
        logger.info('Waking up display')
        try:
            # We explicitly pass the display environment variable
            subprocess.run(['xset', '-display', ':0', 'dpms', 'force', 'on'], check=False)
        except Exception as e:
            logger.error('Failed to turn on display: %s', e)

    def _turn_off(self) -> None:
        logger.info('Turning off display (timeout reached)')
        try:
            # First ensure DPMS is enabled, as 'xset -dpms' in the setup script disables it,
            # which might prevent 'force off' from working on some X servers.
            subprocess.run(['xset', '-display', ':0', '+dpms'], check=False)
            subprocess.run(['xset', '-display', ':0', 'dpms', 'force', 'off'], check=False)
        except Exception as e:
            logger.error('Failed to turn off display: %s', e)

    def start(self) -> None:
        """Start the background thread that monitors timeouts."""
        # Only start the thread if a timeout is configured and > 0
        if self.timeout <= 0:
            return

        t = threading.Thread(target=self._run, daemon=True, name='display-manager')
        t.start()

    def _run(self) -> None:
        while True:
            time.sleep(1)
            with self.lock:
                if self.is_on and (time.monotonic() - self.last_activity > self.timeout):
                    self._turn_off()
                    self.is_on = False
