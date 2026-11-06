"""Run Python tests with real socket connections restricted to loopback.

Protects against accidentally contacting a router or internet service from a
unit test. Local HTTP/MQTT test servers remain usable; transports can be mocked.
"""
import ipaddress
from pathlib import Path
import socket
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex


def require_loopback(address):
    if not isinstance(address, tuple):
        raise OSError('Non-IP socket connection blocked in tests')
    try:
        allowed = ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        allowed = address[0] == 'localhost'
    if not allowed:
        raise OSError('Non-loopback network connection blocked in tests')


def connect(sock, address):
    require_loopback(address)
    return original_connect(sock, address)


def connect_ex(sock, address):
    require_loopback(address)
    return original_connect_ex(sock, address)


if __name__ == '__main__':
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
