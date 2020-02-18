"""Support for LIRC socket."""
# pylint: disable=no-member, import-error
import socket
import errno
import logging
import threading
import time

import voluptuous as vol
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT

)
from homeassistant.helpers import event
from homeassistant.core import Event
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP
)

_LOGGER = logging.getLogger(__name__)
BUTTON_NAME = "button_name"
BUTTON_ALT = "button_alt"
REMOTE = "remote"
FUTURE_EVENT_FIRE_TIMER = 0.3

DOMAIN = "lirc_socket"
CONF_REMOTE = "remote"
CONF_LONG_PRESS_THRESHOLD = "long_press_count"
EVENT_IR_COMMAND_RECEIVED = "ir_command_received"
EVENT_IR_INTERNAL_LONG_PRESS = "ir_internal_long_press"
EVENT_IR_COMMAND_RECEIVED = "ir_command_received"

ICON = "mdi:remote"

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=8765): cv.port,
        vol.Optional(CONF_REMOTE): cv.string,
        vol.Optional(CONF_LONG_PRESS_THRESHOLD, default=5): cv.positive_int
    })},
    extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    component_config = config.get(DOMAIN)
    host = component_config.get(CONF_HOST)
    port = component_config.get(CONF_PORT)
    remote = component_config.get(CONF_REMOTE)
    long_press_threshold = component_config.get(CONF_LONG_PRESS_THRESHOLD)

    try:
        sock = socket.socket()
        sock.connect((host, port))
    except socket.gaierror:
        _LOGGER.error("host configured is not valid")
        return False
    except Exception as e:
        _LOGGER.error("except: %s", e)
        raise PlatformNotReady
    finally:
        sock.close()
    LircSocketInterface(hass, host, port, remote, long_press_threshold)
    return True


class LircSocketInterface():
    def __init__(self, hass, host, port, remote_topic, long_press_threshold):
        self.listener = LircSocketListener(
            hass, host, port, remote_topic, long_press_threshold)
        self.hass = hass
        self._current_event = None
        self._task_cancel = None
        hass.bus.listen_once(
            EVENT_HOMEASSISTANT_START, self.listener.start_listen)
        hass.bus.listen_once(
            EVENT_HOMEASSISTANT_STOP, self.listener.shutdown)
        hass.bus.listen(
            EVENT_IR_INTERNAL_LONG_PRESS, self.__long_press_handler)

    def __gen_end_event(self, now=None):
        evt = self._current_event
        evt_data = evt.data
        evt_data[BUTTON_ALT] = "end"
        self.hass.bus.fire(EVENT_IR_COMMAND_RECEIVED, evt_data)

    def __long_press_handler(self, evt: Event):
        key_sym = evt.data.get(BUTTON_NAME)
        remote = evt.data.get(REMOTE)
        if (self._current_event is not None and
            self._task_cancel is not None and
            key_sym == self._current_event.data.get(BUTTON_NAME) and
            remote == self._current_event.data.get(REMOTE)):
            # cancel postponed task
            self._task_cancel()
        self._current_event = evt
        self._task_cancel = event.async_call_later(
            self.hass, FUTURE_EVENT_FIRE_TIMER,
            self.__gen_end_event)


class LircSocketListener(threading.Thread):
    """
    This interfaces with the lirc daemon to read IR commands.

    When using lirc in blocking mode, sometimes repeated commands get produced
    in the next read of a command so we use a thread here to just wait
    around until a non-empty response is obtained from lirc.
    """

    def __init__(self, hass, host, port, remote_topic, long_press_threshold):
        """Construct a LIRC interface object."""
        threading.Thread.__init__(self)
        self.daemon = True
        self.stopped = threading.Event()
        self.host = host
        self.port = port
        self._available = False
        self.remote = remote_topic
        self.long_press_threshold = long_press_threshold
        self.hass = hass
        self.sock = None

    # deprecated
    def start_listen(self, event):
        """Start event-processing thread."""
        _LOGGER.debug("Event processing thread started")
        self.start()

    def shutdown(self, event):
        if self.sock:
            self.sock.close()

    def __init_sock(self, host, port):
        if self._available:
            return
        tries = 0
        while True:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.settimeout(None)
            except socket.error as exc:
                tries += 1
                wait_time = min(tries, 18) * 10
                _LOGGER.warn(
                    "Error during connection setup: %s (retrying in %s seconds)",
                    exc, wait_time
                )
                time.sleep(wait_time)
            else:
                self._available = True
                break
        self.sock = sock
        self.sfd = sock.makefile('rb')
        _LOGGER.info("lirc socket connected")
        return

    def run(self):
        """Run the loop of the LIRC interface thread."""
        self.__init_sock(self.host, self.port)
        while True:
            try:
                code = self.sfd.readline().decode("ascii").strip()
                if not code:
                    raise ConnectionError
                (hex_code, cnt, key_sym, remote) = code.split(" ")
            except (ConnectionError, socket.error) as e:
                if e.args:
                    err = e.args[0]
                    _LOGGER.warn(
                        "lirc socket connect lost will retry to connect, errno [%d]", err)
                    if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                        continue
                _LOGGER.warn(
                    "lirc socket connect lost will retry to connect", )
                self._available = False
                self.__init_sock(self.host, self.port)
                continue
            except Exception as e:
                _LOGGER.warn("Error while receive data: %s", e)
                continue

            if self.remote is not None \
               and remote.lower() != self.remote.lower():
                _LOGGER.info(
                    "remote [%s] filterd accroding to configuration "
                    % remote)
                continue

            cnt = int(cnt, 16)
            evt_data = {
                BUTTON_NAME: key_sym,
                BUTTON_ALT: None,
                REMOTE: remote
            }
            if cnt == 0:
                evt_data[BUTTON_ALT] = "short"
            elif cnt >= self.long_press_threshold:
                evt_data[BUTTON_ALT] = "long"
                self.hass.bus.fire(
                    EVENT_IR_INTERNAL_LONG_PRESS, evt_data)
            button_alt = evt_data[BUTTON_ALT]
            if button_alt is not None and \
               (button_alt == "short" or
                (button_alt == "long" and
                 cnt == self.long_press_threshold)):
                self.hass.bus.fire(
                    EVENT_IR_COMMAND_RECEIVED, evt_data)
