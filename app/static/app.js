'use strict';
const $ = id => document.getElementById(id);
let statusData = null;
let csrf = null;
let authenticated = false;
let pendingAction = null;
let busyStatus = false;
let toastTimer;
const musicalURL = new URL(location.href);
musicalURL.port = '9000';
musicalURL.protocol = 'http:';
musicalURL.pathname = '/';
musicalURL.search = musicalURL.hash = '';
const musicURL = new URL('material/', musicalURL).href;
const settingsURL = new URL('settings/index.html', musicalURL).href;
document.querySelectorAll('.music-link').forEach(a => a.href = musicURL);
document.querySelectorAll('.lms-settings-link').forEach(a => a.href = settingsURL);
$('lms-address').textContent = musicalURL.href;
$('sonora-address').textContent = location.origin;

function text(id, value) { $(id).textContent = String(value ?? '—'); }
function node(tag, className, content) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (content !== undefined) el.textContent = String(content);
  return el;
}
function icon(kind) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', kind === 'folder' ? 'M3 6h7l2 2h9v12H3Z' : kind === 'server' ? 'M3 4h18v6H3Zm0 10h18v6H3Zm3-7h1m-1 10h1m7-10h4m-4 10h4' : 'M3 5h18v14H3Zm11 5h4m-4 4h4M6 9h4v6H6Z');
  svg.append(path);
  return svg;
}
function notify(message) {
  text('toast', message); $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 5000);
}
async function api(path, body, method = 'POST') {
  const options = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' };
  if (csrf) options.headers['X-Sonora-CSRF'] = csrf;
  if (method !== 'GET') options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  let value;
  try { value = await response.json(); } catch { throw new Error('El equipo no ha podido responder.'); }
  if (!response.ok) {
    if (response.status === 401) { authenticated = false; csrf = null; renderSession(); }
    throw new Error(value.error || 'No se pudo completar la operación.');
  }
  return value;
}
function renderSession() {
  const span = $('admin-toggle').querySelector('span');
  span.textContent = authenticated ? 'Cerrar sesión de ajustes' : 'Desbloquear ajustes';
  $('admin-toggle').title = span.textContent;
}
function requireAdmin(action) {
  if (authenticated) return action();
  pendingAction = action;
  text('login-error', ''); $('admin-password').value = '';
  $('login-dialog').showModal(); $('admin-password').focus();
}
function showView(view) {
  const names = { overview: 'Vista general', audio: 'Audio y salida', sources: 'Fuentes musicales', connect: 'Apps y conexión' };
  if (!(view in names)) return;
  document.querySelectorAll('.page-view').forEach(el => el.hidden = el.id !== 'view-' + view);
  document.querySelectorAll('nav [data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  text('section-name', names[view]);
  history.replaceState(null, '', '#' + view); window.scrollTo({ top: 0 });
}
document.querySelectorAll('[data-view]').forEach(el => el.addEventListener('click', () => showView(el.dataset.view)));
showView(location.hash.slice(1) || 'overview');

function formatNumber(value) {
  const num = Number(value);
  return value === undefined || value === null || !Number.isFinite(num) ? '—' : new Intl.NumberFormat('es-CL').format(num);
}
function rateLabel(value) {
  if (value === undefined || value === null || value === '') return null;
  const plain = String(value).split(' ')[0];
  const n = Number(plain);
  if (!Number.isFinite(n)) return String(value);
  return n > 1000 ? new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 }).format(n / 1000) + ' kHz' : String(value);
}
function selectedHW(data) {
  const selected = data.devices.find(d => d.id === data.audio.device);
  return data.hardware_streams.find(h => selected && h.card === 'card' + selected.card) || null;
}
function renderPlayback(data) {
  const track = data.track || {};
  const playback = data.playback || {};
  const playing = playback.mode === 'play';
  const paused = playback.mode === 'pause';
  $('playback-label').replaceChildren(node('i'), document.createTextNode(playing ? ' AHORA SUENA' : paused ? ' EN PAUSA' : ' TU SALA DE ESCUCHA'));
  text('track-overline', track.album || (playing ? 'AHORA EN TU SALA' : 'AQUÍ EMPIEZA TU PRÓXIMO ÁLBUM'));
  text('track-title', track.title || 'Dale espacio a la música.');
  text('track-subtitle', track.artist || (track.title ? track.album || 'Tu colección musical' : 'Abre la biblioteca y elige qué quieres escuchar. Sonora se encarga del resto.'));
  const format = [track.type, rateLabel(track.samplerate), track.sample_size ? track.sample_size + ' bit' : null].filter(Boolean).join(' · ');
  text('track-format', format || 'MÚSICA EN CASA');
  const link = $('track-link'); link.replaceChildren(document.createTextNode(track.title ? 'Abrir reproducción ' : 'Elegir música '), node('span', '', '↗'));
  text('playback-detail', playing ? 'Reproduciendo' : paused ? 'En pausa' : 'Reproductor local');
  text('signal-source', track.type ? String(track.type).toUpperCase() : 'Fuente musical');
  text('signal-source-detail', format || 'Local, NAS o servicio conectado');
}
function renderDevices(data) {
  const list = $('device-list'); list.replaceChildren();
  if (!data.devices.length) {
    const empty = node('div', 'empty-box'); empty.append(icon('device'), node('b', '', 'Conecta un DAC USB.'), node('p', '', 'La salida aparecerá aquí cuando el equipo la reconozca.'));
    list.append(empty);
  }
  const sorted = [...data.devices].sort((a, b) => Number(b.usb) - Number(a.usb));
  sorted.forEach(device => {
    const selected = device.id === data.audio.device;
    const row = node('div', 'device-option' + (selected ? ' selected' : ''));
    const copy = node('div'); copy.append(node('b', '', device.name), node('small', '', (device.usb ? 'USB · ' : 'Salida integrada · ') + device.id));
    row.append(icon('device'), copy);
    if (selected) row.append(node('span', 'selected-label', 'Seleccionada ✓'));
    else {
      const button = node('button', '', 'Seleccionar');
      button.addEventListener('click', () => requireAdmin(async () => {
        button.disabled = true;
        try { await api('/api/audio', { device: device.id }); notify('Salida de audio actualizada.'); await refreshStatus(); }
        catch (err) { notify(err.message); }
        finally { button.disabled = false; }
      }));
      row.append(button);
    }
    list.append(row);
  });
  const current = data.devices.find(d => d.id === data.audio.device);
  text('footer-audio', current?.name || data.audio.name || (data.audio.device ? 'Salida configurada' : 'Sin salida de audio seleccionada'));
  text('signal-dac', current?.name || data.audio.name || 'Salida de audio');
  const hardware = selectedHW(data);
  text('signal-dac-detail', hardware ? [rateLabel(hardware.rate), hardware.format, hardware.channels ? hardware.channels + ' canales' : null].filter(Boolean).join(' · ') : current ? (current.usb ? 'DAC USB · esperando reproducción' : 'Dispositivo conectado · esperando reproducción') : 'Conecta un DAC USB');
  text('alsa-format', hardware?.format || 'Sin reproducción');
  text('alsa-rate', rateLabel(hardware?.rate) || 'Sin reproducción');
  const isPure = data.audio.mode === 'pure';
  text('mode-value', isPure ? 'Puro' : data.audio.mode === 'listening' ? 'Escucha' : 'Sin configurar');
  text('volume-value', data.audio.volume_fixed === true ? 'Activado' : data.audio.volume_fixed === false ? 'Desactivado' : 'Sin comprobar');
  text('pure-badge', isPure ? 'PERFIL PURO' : data.audio.mode === 'listening' ? 'PERFIL ESCUCHA' : 'CONFIGURACIÓN');
  text('profile-title', isPure ? 'Modo puro' : data.audio.mode === 'listening' ? 'Modo escucha' : 'Tu perfil de audio');
  text('profile-description', isPure ? 'Sin ecualización ni remuestreo forzado. Controla el nivel desde tu DAC o amplificador: el volumen digital está fijo.' : 'Volumen y ReplayGain configurables desde Lyrion. Elige el nivel que te resulte cómodo para escuchar.');
  document.querySelectorAll('[data-profile]').forEach(button => {
    button.classList.toggle('active', button.dataset.profile === data.audio.mode);
    button.disabled = button.dataset.profile === data.audio.mode;
  });
  text('signal-note', hardware ? 'Parámetros activos comunicados por ALSA. No son una certificación de identidad de las muestras.' : 'Los datos de salida aparecen cuando el dispositivo está reproduciendo.');
}
function renderSources(data) {
  const list = $('nas-list'); list.replaceChildren();
  if (!data.sources.length) {
    const empty = node('div', 'empty-box'); empty.append(icon('server'), node('b', '', 'Tu colección está esperando.'), node('p', '', 'Añade la carpeta de música de tu NAS para que forme parte de la biblioteca.')); list.append(empty);
  }
  data.sources.forEach(source => {
    const row = node('div', 'nas-source'), copy = node('div'), symbol = node('span', 'source-icon'); symbol.append(icon('server'));
    copy.append(node('b', '', source.name), node('small', '', source.host + '/' + source.share));
    const state = node('span', 'source-state' + (source.mounted ? ' online' : '')); state.append(node('i'), document.createTextNode(source.mounted ? 'Conectada' : 'No montada'));
    row.append(symbol, copy, state); list.append(row);
  });
}
function renderPlayers(data) {
  const list = $('players-list'); list.replaceChildren();
  if (!data.players.length) return list.append(node('div', 'empty-box', 'El reproductor aparecerá cuando se conecte al servidor musical.'));
  data.players.forEach(player => {
    const row = node('div', 'player-row'); row.append(icon('device'), node('b', '', player.name || 'Reproductor'), node('small', '', Number(player.connected) ? 'Conectado' : 'Sin conexión')); list.append(row);
  });
}
async function refreshStatus() {
  if (busyStatus) return;
  busyStatus = true;
  try {
    const data = await api('/api/status', null, 'GET');
    data.devices = Array.isArray(data.devices) ? data.devices : [];
    data.hardware_streams = Array.isArray(data.hardware_streams) ? data.hardware_streams : [];
    data.sources = Array.isArray(data.sources) ? data.sources : [];
    data.players = Array.isArray(data.players) ? data.players : [];
    data.audio = data.audio || {}; data.services = data.services || {}; data.library = data.library || {};
    statusData = data;
    const connected = data.services.lyrionmusicserver === true;
    text('connection-text', connected ? 'Servidor disponible' : 'Servidor musical detenido');
    $('connection-led').className = connected ? 'status-online' : 'status-warning';
    $('sidebar-led').className = 'device-led ' + (connected ? 'status-online' : 'status-warning');
    text('sidebar-host', data.hostname || 'Sonora'); text('sidebar-state', connected ? 'Listo para escuchar' : 'Servidor musical detenido');
    text('version', data.version || '0.1');
    text('album-count', formatNumber(data.library.albums)); text('track-count', formatNumber(data.library.tracks)); text('artist-count', formatNumber(data.library.artists));
    text('library-scan', Number(data.library.scanning) ? 'Actualizando la biblioteca…' : 'Biblioteca musical');
    renderPlayback(data); renderDevices(data); renderSources(data); renderPlayers(data);
    text('last-update', 'Actualizado a las ' + new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' }));
    $('error-banner').hidden = true;
  } catch (err) {
    text('error-banner', 'No podemos leer el estado del equipo. ' + err.message); $('error-banner').hidden = false;
    text('connection-text', 'Sin conexión'); $('connection-led').className = 'status-warning';
    text('sidebar-state', 'No se puede leer el estado'); $('sidebar-led').className = 'device-led status-warning';
  } finally { busyStatus = false; }
}
$('admin-toggle').addEventListener('click', async () => {
  if (!authenticated) return requireAdmin(() => notify('Ajustes desbloqueados.'));
  try { await api('/api/logout', {}); authenticated = false; csrf = null; renderSession(); notify('Sesión de ajustes cerrada.'); }
  catch (err) { notify(err.message); }
});
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; text('login-error', '');
  try {
    const result = await api('/api/session', { password: $('admin-password').value });
    $('admin-password').value = ''; authenticated = true; csrf = result.csrf; renderSession(); $('login-dialog').close();
    const action = pendingAction; pendingAction = null; if (action) await action();
  } catch (err) { text('login-error', err.message); }
  finally { button.disabled = false; }
});
$('login-dialog').addEventListener('close', () => { $('admin-password').value = ''; pendingAction = null; });
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
$('nas-add-button').addEventListener('click', () => requireAdmin(() => { text('nas-error', ''); $('nas-dialog').showModal(); $('nas-form').elements.name.focus(); }));
$('nas-dialog').addEventListener('close', () => { $('nas-form').elements.password.value = ''; });
$('nas-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; text('nas-error', '');
  const body = Object.fromEntries(new FormData(event.currentTarget));
  try { await api('/api/nas', body); $('nas-dialog').close(); $('nas-form').reset(); notify('Carpeta conectada. Actualiza la biblioteca para añadir su música.'); await refreshStatus(); }
  catch (err) { text('nas-error', err.message); }
  finally { body.password = ''; $('nas-form').elements.password.value = ''; button.disabled = false; }
});
$('rescan-button').addEventListener('click', () => requireAdmin(async () => {
  $('rescan-button').disabled = true;
  try { const result = await api('/api/rescan', {}); notify(result.message); await refreshStatus(); }
  catch (err) { notify(err.message); }
  finally { $('rescan-button').disabled = false; }
}));
async function changeProfile(mode) {
  try { await api('/api/profile', { mode }); notify(mode === 'pure' ? 'Modo puro activado. Controla el volumen desde el DAC o amplificador.' : 'Modo escucha activado. Ajusta el volumen desde tu app.'); await refreshStatus(); }
  catch (err) { notify(err.message); }
}
document.querySelectorAll('[data-profile]').forEach(button => button.addEventListener('click', () => requireAdmin(async () => {
  if (button.dataset.profile === 'pure') $('confirm-dialog').showModal();
  else await changeProfile('listening');
})));
$('confirm-form').addEventListener('submit', async event => { event.preventDefault(); $('confirm-dialog').close(); await changeProfile('pure'); });
$('diagnostics').addEventListener('click', () => {
  if (!statusData) return notify('Espera a que el equipo responda antes de guardar el diagnóstico.');
  const report = { at: new Date().toISOString(), ...statusData };
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), url = URL.createObjectURL(blob);
  const a = node('a'); a.href = url; a.download = 'sonora-diagnostico.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  notify('Diagnóstico descargado. No incluye contraseñas ni tokens de acceso.');
});
document.querySelectorAll('.copy-address').forEach(button => button.addEventListener('click', async () => {
  const address = button.dataset.address === 'lms' ? musicalURL.href : location.origin;
  try { await navigator.clipboard.writeText(address); notify('Dirección copiada.'); }
  catch { notify('Dirección del equipo: ' + address); }
}));
api('/api/session', null, 'GET').then(result => { authenticated = result.authenticated; csrf = result.csrf; renderSession(); }).catch(() => {});
refreshStatus(); setInterval(() => { if (!document.hidden) refreshStatus(); }, 15000);
