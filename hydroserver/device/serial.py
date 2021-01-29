import enum
import glob
import logging
import termios
import threading
import time

from serial import Serial, SerialException

from hydroserver.device import Device, DeviceType, DeviceException
from hydroserver import Config


log = logging.getLogger(__name__)

# CONSTANTS
baud_rate = Config.BAUD_RATE
serial_prefix = Config.SERIAL_PREFIX


class DeviceSerialException(DeviceException):
    """Something wrong with serial connection"""
    pass


class DeviceNotFoundException(DeviceSerialException):
    """File not found - not connected"""
    pass


class DeviceNotRespondingException(DeviceException):
    """Serial works, but we're not receiving expected data"""
    pass


class SerialDevice(Device):

    device_type = DeviceType.ARDUINO_UNO
    TIMEOUT = 5
    WAIT_FOR_RESPONSE = 0.1

    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.lock = threading.Lock()
        self.serial = None
        self.__uuid = None

        self.__init_serial()

    def _get_uuid(self):
        return self.__uuid

    def __init_serial(self):
        log.info("Initializing {}...".format(self))
        try:
            self.serial = Serial(self.port, self.baud, timeout=self.TIMEOUT)
            time.sleep(2)  # fixme: serial takes time to be ready to receive

            device_info = self.read_status()
            if device_info:
                if "uuid" in device_info.data.keys():
                    self.__uuid = device_info.data['uuid']
                else:
                    log.warning("Device info received, but without UUID field")
            else:
                log.warning("Device info not received.")
        except (FileNotFoundError, SerialException) as e:
            log.error("Failed to open serial connection: {}".format(e))
            self.serial = None

    # [!] one and only send method
    def __send(self, serial, command, wait_for_response=WAIT_FOR_RESPONSE):
        with self.lock:
            try:
                serial.flush()
                to_write = "{}\n".format(command).encode("utf-8")
                serial.write(to_write)
                time.sleep(wait_for_response)
                response = serial.readline().decode("utf-8").rstrip()
                if not response:
                    self.__uuid = None
                    log.warning(
                        "{}: response for '{}' not received..".format(self, command))
                return response
            except SerialException as e:
                log.warning(e.strerror)
                self.__uuid = None
            except termios.error as e:
                log.fatal("{}: device got probably disconnected".format(e))
                self.__uuid = None
                self.serial = None

    def reset_serial(self):
        self.serial = None

    def _send_raw(self, string):
        if not self.is_connected:
            log.warning(f"{self} is not connected")
            self.__init_serial()
            if not self.serial:
                log.error(f"{self}: reconnect failed.")
                return

        return self.__send(self.serial, string)

    @property
    def is_connected(self):
        return self.serial is not None

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{super().__repr__()[:-2]}, port={self.port}, baud={self.baud}"


def get_connected_devices():
    devices = glob.glob("/dev/{}*".format(serial_prefix))
    log.info("Connected devices (prefix '{}'): {}".format(serial_prefix, devices))
    return devices


def scan(exclude=None):
    """
    Run scan for all configured serial ports
    """
    if not exclude:
        exclude = []
    log.info("Scanning for serial devices...")
    found_devices = []
    for port in get_connected_devices():
        if port in exclude:
            log.info("{}: skipping...".format(port))
            continue
        try:
            device = SerialDevice(port, baud_rate)
        except SerialException as e:
            log.warning(e)
            continue
        if device.is_responding:
            found_devices.append(device)
        else:
            log.warning("{} not responding.".format(device))
    log.info("Scan complete, found devices: {}".format(found_devices))
    return found_devices

