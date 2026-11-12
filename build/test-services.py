#!/usr/bin/env python3
"""Read-only health check for a newly booted, task-owned Sonora guest."""
import argparse
import json
import http.client
import time
import urllib.request
from datetime import datetime, timezone


def request(url, command, player=''):
    body = json.dumps({'id': 1, 'method': 'slim.request', 'params': [player, command]}).encode()
    req = urllib.request.Request(url.rstrip('/') + '/jsonrpc.js', data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=4) as response:
        parsed = json.load(response)
    if parsed.get('error'):
        raise RuntimeError(parsed['error'])
    return parsed.get('result', {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lms-url', default='http://127.0.0.1:19000')
    parser.add_argument('--portal-url', default='http://127.0.0.1:19080')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--output')
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    last_error = None
    server = players = None
    ready = False
    while time.monotonic() < deadline:
        try:
            server = request(args.lms_url, ['version', '?'])
            players = request(args.lms_url, ['players', '0', '20'])
            with urllib.request.urlopen(args.portal_url, timeout=4) as response:
                status = response.status
                html = response.read().decode('utf-8', errors='replace')
            with urllib.request.urlopen(args.lms_url.rstrip('/') + '/material/', timeout=4) as response:
                material_status = response.status
            if status != 200 or material_status != 200:
                raise RuntimeError('Waiting for all guest HTTP services')
            if not any(player.get('connected') for player in players.get('players_loop', [])):
                raise RuntimeError('Waiting for the virtual USB Squeezelite player')
            ready = True
            break
        except (OSError, http.client.HTTPException, RuntimeError, ValueError) as error:
            last_error = str(error)
            time.sleep(2)
    if not ready:
        raise SystemExit('LMS did not become ready: ' + str(last_error))
    result = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'lms_version': server,
        'players': players,
        'portal_http_status': status,
        'portal_has_sonora_branding': 'sonora' in html.lower(),
        'material_http_status': material_status,
        'guest_ready': status == 200 and material_status == 200,
        'scope': 'Virtual BIOS/UEFI guest health; no physical DAC or streaming account assertion.'
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as handle:
            handle.write(text + '\n')
    print(text)
    if not result['guest_ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
