#!/usr/bin/env python3
"""Sonora's local appliance console. Music playback is handled by Lyrion."""
from __future__ import annotations
import argparse
import hashlib
import hmac
import http.cookies
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BODY = 16_384
SESSION_SECONDS = 1800
DEVICE_RE = re.compile(r"hw:CARD=[A-Za-z0-9_-]{1,64},DEV=[0-9]{1,2}\Z")
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
STATIC = Path(__file__).resolve().parent / 'static'
LOG = logging.getLogger('sonora')

class APIError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def strict_object(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        raise APIError('Los datos enviados no tienen el formato esperado.')
    if any(not isinstance(v, str) for v in value.values()):
        raise APIError('Los campos deben ser texto.')
    if any(any(ord(c) < 32 or ord(c) == 127 for c in v) for v in value.values()):
        raise APIError('Los campos contienen caracteres no válidos.')
    return value


def validate_nas(value):
    value = strict_object(value, ('name', 'host', 'share'), ('username', 'password', 'domain'))
    name, host, share = value['name'], value['host'], value['share']
    if not NAME_RE.fullmatch(name):
        raise APIError('El nombre admite hasta 32 letras, números, guiones y guiones bajos.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
            raise APIError('Escribe una dirección IP o un nombre de servidor válido.')
        if any(not part or len(part) > 63 or part.startswith('-') or part.endswith('-') for part in host.split('.')):
            raise APIError('El nombre del servidor no es válido.')
    if not share or len(share) > 512 or share.startswith(('/', '\\')) or '\\' in share or any(p in ('', '.', '..') for p in share.split('/')):
        raise APIError('La carpeta compartida debe ser una ruta relativa sin puntos de navegación.')
    for field in ('username', 'password', 'domain'):
        if len(value.get(field, '')) > (512 if field == 'password' else 128):
            raise APIError('Uno de los campos supera la longitud admitida.')
    return value


def json_file(path, fallback):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return fallback


def command(argv, timeout=4, input_text=None):
    return subprocess.run(argv, input=input_text, text=True, capture_output=True, timeout=timeout, check=False)


def lms_request(args, player=''):
    payload = json.dumps({'id': 1, 'method': 'slim.request', 'params': [player, args]}).encode()
    req = Request('http://127.0.0.1:9000/jsonrpc.js', data=payload, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=3) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Respuesta musical demasiado grande')
    result = json.loads(raw)
    if result.get('error'):
        raise ValueError('Lyrion rechazó la solicitud')
    return result.get('result', {})


def read_hw_params(proc_root=Path('/proc/asound')):
    result = []
    for path in sorted(proc_root.glob('card[0-9]*/pcm[0-9]*p/sub[0-9]*/hw_params')):
        try:
            text = path.read_text()
            if text.strip() == 'closed':
                continue
            fields = {}
            for line in text.splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    fields[k.strip()] = v.strip()[:160]
            result.append({'card': path.parent.parent.parent.name, 'pcm': path.parent.parent.name,
                           **{k: fields[k] for k in ('format', 'channels', 'rate', 'access') if k in fields}})
        except OSError:
            continue
    return result


def audio_devices(proc_root=Path('/proc/asound')):
    try:
        output = command(['/usr/bin/aplay', '-l']).stdout
    except (OSError, subprocess.TimeoutExpired):
        output = ''
    devices = []
    for line in output.splitlines():
        match = re.match(r'^card\s+(\d+):\s+([A-Za-z0-9_-]+)\s+\[(.*?)\],\s+device\s+(\d+):\s+(.*?)\s*\[(.*?)\]', line)
        if not match:
            continue
        number, card, name, dev, detail, _ = match.groups()
        is_usb = (proc_root / ('card' + number) / 'usbid').exists()
        devices.append({'id': f'hw:CARD={card},DEV={dev}', 'name': name, 'detail': detail,
                        'card': int(number), 'usb': is_usb})
    return devices


def safe_sources(config_dir):
    raw = json_file(config_dir / 'nas.json', [])
    if isinstance(raw, dict):
        raw = raw.get('shares', [])
    result = []
    if not isinstance(raw, list):
        return result
    for source in raw:
        if not isinstance(source, dict):
            continue
        result.append({key: str(source.get(key, ''))[:512] for key in ('name', 'host', 'share', 'path')})
        path = result[-1]['path'] or '/srv/music/nas/' + result[-1]['name']
        result[-1]['mounted'] = os.path.ismount(path)
    return result


class Context:
    def __init__(self, config_dir=Path('/etc/sonora')):
        self.config_dir = Path(config_dir)
        self.sessions = {}
        self.failures = {}
        self.lock = threading.Lock()
        self.started = time.monotonic()

    def authenticate(self, password, ip):
        now = time.monotonic()
        with self.lock:
            history = [v for v in self.failures.get(ip, []) if now - v < 60]
            if len(history) >= 5:
                raise APIError('Espera un minuto antes de volver a intentar.', 429)
            self.failures[ip] = history
        record = json_file(self.config_dir / 'admin.json', {})
        try:
            iterations = int(record.get('iterations', 200000))
            if iterations < 100_000 or iterations > 2_000_000:
                raise ValueError('invalid iterations')
            salt = bytes.fromhex(record['salt'])
            expected = bytes.fromhex(record['hash'])
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
            valid = len(salt) >= 16 and len(expected) == 32 and hmac.compare_digest(expected, actual)
        except (KeyError, ValueError, TypeError):
            raise APIError('La administración aún no tiene contraseña. Revisa la pantalla del equipo.', 503)
        if not valid:
            with self.lock:
                self.failures[ip].append(now)
            raise APIError('La contraseña no es correcta.', 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
            if len(self.sessions) >= 50:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[token] = {'csrf': csrf, 'expires': now + SESSION_SECONDS}
            self.failures.pop(ip, None)
        return token, csrf

    def session(self, cookie):
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(cookie or '')
            token = jar['sonora_session'].value
        except (KeyError, http.cookies.CookieError):
            return None, None
        with self.lock:
            item = self.sessions.get(token)
            if not item or item['expires'] <= time.monotonic():
                self.sessions.pop(token, None)
                return None, None
            return token, item

    def status(self):
        audio = json_file(self.config_dir / 'audio.json', {})
        audio = audio if isinstance(audio, dict) else {}
        safe_audio = {k: audio[k] for k in ('device', 'name', 'mode', 'volume_fixed') if k in audio}
        info = {'hostname': socket.gethostname(), 'version': '0.1.0', 'audio': safe_audio,
                'devices': audio_devices(), 'hardware_streams': read_hw_params(),
                'sources': safe_sources(self.config_dir), 'services': {}, 'library': {}, 'players': []}
        try:
            boot = Path('/proc/uptime').read_text().split()[0]
            info['uptime_seconds'] = int(float(boot))
        except (OSError, ValueError, IndexError):
            info['uptime_seconds'] = int(time.monotonic() - self.started)
        for service, unit in (('lyrionmusicserver', 'lyrionmusicserver.service'), ('squeezelite', 'sonora-player.service')):
            try:
                info['services'][service] = command(['/usr/bin/systemctl', 'is-active', unit], 2).stdout.strip() == 'active'
            except (OSError, subprocess.TimeoutExpired):
                info['services'][service] = False
        try:
            data = lms_request(['serverstatus', '0', '100'])
            info['services']['lyrionmusicserver'] = True
            info['library'] = {k: data.get(v) for k, v in [('tracks', 'info total songs'), ('albums', 'info total albums'), ('artists', 'info total artists'), ('scanning', 'rescan')] if v in data}
            for player in data.get('players_loop', [])[:100]:
                if not isinstance(player, dict):
                    continue
                result = {k: player[k] for k in ('playerid', 'name', 'connected', 'model') if k in player}
                info['players'].append(result)
            player_config = json_file(self.config_dir / 'player.json', {})
            local_id = str(player_config.get('id', '')).casefold() if isinstance(player_config, dict) else ''
            selected = next((p for p in info['players'] if local_id and str(p.get('playerid', '')).casefold() == local_id), None)
            if selected:
                state = lms_request(['status', '-', '1', 'tags:aldorTIH'], selected['playerid'])
                info['playback'] = {k: state[k] for k in ('mode', 'time', 'duration', 'mixer volume', 'playlist_tracks') if k in state}
                tracks = state.get('playlist_loop', [])
                if tracks and isinstance(tracks[0], dict):
                    info['track'] = {k: tracks[0][k] for k in ('title', 'artist', 'album', 'duration', 'bitrate', 'samplerate', 'type') if k in tracks[0]}
                    if 'samplesize' in tracks[0]:
                        info['track']['sample_size'] = tracks[0]['samplesize']
        except (OSError, ValueError, URLError, TimeoutError, KeyError):
            pass
        return info


class Handler(BaseHTTPRequestHandler):
    server_version = 'Sonora'
    sys_version = ''

    @property
    def ctx(self):
        return self.server.context

    def setup(self):
        super().setup()
        self.connection.settimeout(12)

    def log_message(self, fmt, *args):
        # Request bodies, query strings and authentication values are never logged.
        LOG.info('%s %s', self.command, self.path.split('?', 1)[0])

    def response(self, code, body, content_type='application/json; charset=utf-8', cookie=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store' if 'json' in content_type else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('X-Frame-Options', 'DENY')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def error(self, exc):
        self.response(exc.status, {'error': exc.message})

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path in ('/api/status', '/status'):
                return self.response(200, self.ctx.status())
            if path == '/api/session':
                _, session = self.ctx.session(self.headers.get('Cookie'))
                return self.response(200, {'authenticated': bool(session), 'csrf': session['csrf'] if session else None})
            static = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
            if path not in static:
                raise APIError('No se encuentra esta página.', 404)
            filename, mime = static[path]
            return self.response(200, (STATIC / filename).read_bytes(), mime)
        except APIError as exc:
            self.error(exc)
        except (OSError, ValueError):
            self.error(APIError('No se pudo leer el estado del equipo.', 503))

    def verify_origin(self):
        origin = self.headers.get('Origin', '')
        host = self.headers.get('Host', '')
        if not host or not re.fullmatch(r'[A-Za-z0-9.\-\[\]:]+', host):
            raise APIError('Origen no válido.', 403)
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or parsed.netloc != host or parsed.path or parsed.query or parsed.fragment:
            raise APIError('Abre los ajustes desde la dirección de este equipo.', 403)

    def read_json(self):
        if self.headers.get_content_type() != 'application/json':
            raise APIError('Se requiere una solicitud JSON.', 415)
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise APIError('Tamaño de solicitud no válido.')
        if size < 0 or size > MAX_BODY:
            raise APIError('La solicitud es demasiado grande.', 413)
        try:
            return json.loads(self.rfile.read(size).decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise APIError('No se pudieron leer los datos enviados.')

    def do_POST(self):
        try:
            self.verify_origin()
            body = self.read_json()
            path = urlsplit(self.path).path
            if path == '/api/session':
                strict_object(body, ('password',))
                if not body['password'] or len(body['password']) > 512:
                    raise APIError('Escribe la contraseña del equipo.', 401)
                token, csrf = self.ctx.authenticate(body['password'], self.client_address[0])
                return self.response(200, {'authenticated': True, 'csrf': csrf}, cookie=f'sonora_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}')
            token, session = self.ctx.session(self.headers.get('Cookie'))
            if not session:
                raise APIError('Introduce la contraseña para cambiar los ajustes.', 401)
            if not hmac.compare_digest(self.headers.get('X-Sonora-CSRF', '').encode(), session['csrf'].encode()):
                raise APIError('La sesión de ajustes ha caducado. Vuelve a entrar.', 403)
            if path == '/api/logout':
                strict_object(body, ())
                with self.ctx.lock:
                    self.ctx.sessions.pop(token, None)
                return self.response(200, {'ok': True}, cookie='sonora_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path == '/api/audio':
                strict_object(body, ('device',))
                if not DEVICE_RE.fullmatch(body['device']) or body['device'] not in {d['id'] for d in audio_devices()}:
                    raise APIError('Elige una salida de audio que esté conectada.')
                proc = command(['/usr/local/sbin/sonoractl', 'audio', '--device', body['device']], timeout=30)
            elif path == '/api/profile':
                strict_object(body, ('mode',))
                if body['mode'] not in ('pure', 'listening'):
                    raise APIError('Elige un perfil de reproducción válido.')
                proc = command(['/usr/local/sbin/sonoractl', 'profile', '--mode', body['mode']], timeout=30)
            elif path == '/api/nas':
                value = validate_nas(body)
                argv = ['/usr/local/sbin/sonoractl', 'nas-add', '--name', value['name'], '--host', value['host'], '--share', value['share'],
                        '--username', value.get('username', ''), '--domain', value.get('domain', '')]
                proc = command(argv, timeout=75, input_text=json.dumps({'password': value.get('password', '')}))
            elif path == '/api/rescan':
                strict_object(body, ())
                lms_request(['rescan'])
                return self.response(200, {'ok': True, 'message': 'La biblioteca se está actualizando.'})
            else:
                raise APIError('Operación no disponible.', 404)
            if proc.returncode:
                # Helpers may include credentials or mount arguments in stderr: never relay them.
                raise APIError('No se pudo aplicar el ajuste. Revisa la conexión o la configuración en la pantalla del equipo.', 422)
            return self.response(200, {'ok': True})
        except APIError as exc:
            self.error(exc)
        except subprocess.TimeoutExpired:
            self.error(APIError('El equipo tardó demasiado en responder. Comprueba su estado antes de volver a intentarlo.', 504))
        except (OSError, ValueError, URLError, TimeoutError):
            self.error(APIError('El servicio no está disponible en este momento.', 503))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description='Consola local de Sonora')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--config-dir', type=Path, default=Path('/etc/sonora'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    server = Server((args.host, args.port), Handler)
    server.context = Context(args.config_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
