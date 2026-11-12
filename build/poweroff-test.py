#!/usr/bin/env python3
"""Request a normal guest shutdown from inside its owned QEMU container."""
import json
import socket
import sys

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/sonora-qmp.sock'
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(10)
    sock.connect(path)
    stream = sock.makefile('rwb', buffering=0)
    json.loads(stream.readline())
    for command in ('qmp_capabilities', 'system_powerdown'):
        stream.write((json.dumps({'execute': command}) + '\n').encode())
        while True:
            response = json.loads(stream.readline())
            if 'return' in response:
                break
            if 'error' in response:
                raise RuntimeError(response['error'])
print('Normal guest shutdown requested.')
