"""Support for LIRC socket."""
# pylint: disable=no-member, import-error
import socket
import logging
import threading
import time

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.components.lirc import (
    BUTTON_NAME,
    EVENT_IR_COMMAND_RECEIVED,
    ICON
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP
)

_LOGGER = logging.getLogger(__name__)

CONNECT_RETRY_WAIT = 10

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=8765): cv.port,
})


async def async_setup_platform(hass, config):

    host = config.get(CONF_NAME)
    port = int(config.get(CONF_PORT))
    lirc_interface = LircInterface(hass, host, port)

    def _start_lirc(_event):
        lirc_interface.start()

    def _stop_lirc(_event):
        lirc_interface.stopped.set()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, _start_lirc)
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, _stop_lirc)

    return True


class LircInterface(threading.Thread):
    """
    This interfaces with the lirc daemon to read IR commands.

    When using lirc in blocking mode, sometimes repeated commands get produced
    in the next read of a command so we use a thread here to just wait
    around until a non-empty response is obtained from lirc.
    """

    def __init__(self, hass, host, port):
        """Construct a LIRC interface object."""
        threading.Thread.__init__(self)
        self.daemon = True
        self.stopped = threading.Event()
        self.host = host
        self.port = port
        self._available = False
        self.hass = hass

    def __init_sock(self, host, port):
        if self._available:
            return
        retry_cnt = 0
        while True:
            sock = None
            try:
                sock = socket.socket()
                sock.connet((host, port))
            except socket.error, exc:
                LOGGER.error(
                    "Error during connection setup: %s (retrying in %s seconds)",
                    err,
                    CONNECT_RETRY_WAIT,
                )
                retry_cnt += 1
                if retry_cnt == 3:
                    CONNECT_RETRY_WAIT = 30
                if retry_cnt == 5:
                    CONNECT_RETRY_WAIT = 60
                if retry_cnt == 10:
                    CONNECT_RETRY_WAIT = 180
                time.sleep(CONNECT_RETRY_WAIT)
            else:
                self._available = True
            self.sock = sock
            return

    def run(self):
        """Run the loop of the LIRC interface thread."""
        _LOGGER.debug("LIRC interface thread started")
        self.__init_sock(self.host, self.port)
        while not self.stopped.isSet():
            try:
                code = self.sock.recv(128)
            except socket.error, e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    code = None
                else:
                    self._available = False
                    self.__init_sock(self.host, self.port)
                    continue
            if code:
                code = code.strip()
                code = code[0]
                _LOGGER.info("Got new LIRC code %s", code)
                self.hass.bus.fire(EVENT_IR_COMMAND_RECEIVED, {BUTTON_NAME: code})
            else:
                time.sleep(0.2)
        socket.close(self.sock)
        _LOGGER.debug("LIRC interface thread stopped")
