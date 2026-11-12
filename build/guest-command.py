#!/usr/bin/env python3
"""Run a diagnostic in an isolated QA guest after verifying its console prompt."""
import argparse
import codecs
import pathlib
import re
import secrets
import socket
import time

p = argparse.ArgumentParser()
p.add_argument('--serial-log', required=True)
p.add_argument('--command', required=True)
p.add_argument('--socket', default='/tmp/sonora-serial.sock')
p.add_argument('--no-logout', action='store_true')
a = p.parse_args()
raw = pathlib.Path(a.serial_log).read_text(errors='replace')
match = re.search(r'Contrase.a del panel y consola local \(root\):\s*([A-Za-z0-9_-]+)', raw)
if not match:
    raise SystemExit('The private QA credential is not yet present in the serial log.')
password = match.group(1)
root_prompt = re.compile(r'root@[^\r\n]*[#]\s*')
login_prompt = re.compile(r'(?i)[^\r\n]*login:\s*')
password_prompt = re.compile(r'(?i)(?:password|contrase.{1,3}a):\s*')

def redact(text):
    text = text.replace(password, '[REDACTED]')
    return re.sub(r'(Contrase.a del panel y consola local \(root\):\s*)[A-Za-z0-9_-]+', r'\1[REDACTED]', text)

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sock.connect(a.socket)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    def collect(seconds):
        end = time.monotonic() + seconds
        text = ''
        while time.monotonic() < end:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                text += decoder.decode(chunk)
            except socket.timeout:
                pass
        return text
    def prompt_state(text):
        matches = []
        for name, pattern in [('root', root_prompt), ('login', login_prompt), ('password', password_prompt)]:
            for found in pattern.finditer(text):
                matches.append((found.start(), name))
        return max(matches)[1] if matches else None
    sock.sendall(b'\n')
    banner = collect(1)
    deadline = time.monotonic() + 20
    sent_user = sent_password = False
    while time.monotonic() < deadline:
        state = prompt_state(banner)
        if state == 'root':
            break
        if state == 'login' and not sent_user:
            sock.sendall(b'root\n')
            sent_user = True
            banner = collect(1)
            continue
        if state == 'password' and not sent_password:
            sock.sendall(password.encode() + b'\n')
            sent_password = True
            banner = collect(1)
            continue
        banner += collect(1)
    else:
        raise SystemExit('The guest did not reach a root prompt; no command was executed.')
    token = 'SONORA_DIAGNOSTIC_DONE_' + secrets.token_hex(6)
    line = a.command + "; printf '\\n" + token + "\\n'\n"
    sock.sendall(line.encode())
    out = ''
    end = time.monotonic() + 15
    marker = re.compile(r'(?:^|\r?\n)' + token + r'(?:\r?\n|$)')
    while time.monotonic() < end:
        out += collect(0.5)
        if marker.search(out):
            break
    if not a.no_logout:
        sock.sendall(b'exit\n')
        # Let getty close this login before another caller connects.
        collect(1)
print(redact(out))
