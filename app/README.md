# Consola Sonora

Consola web local del equipo de audio. La reproducción y la biblioteca musical funcionan en Lyrion Music Server; esta consola configura la salida ALSA, las fuentes SMB y el perfil de reproducción, y muestra el estado disponible del sistema.

## Ejecución

Python 3 estándar, sin dependencias externas:

```sh
python3 /opt/sonora/app/server.py --host 0.0.0.0 --port 80
```

El servicio debe tener los permisos necesarios para leer la configuración y ejecutar `/usr/local/sbin/sonoractl`. La consola se sirve por HTTP en la red local. No se debe publicar su puerto en Internet. Lyrion permanece en el puerto 9000; sus credenciales de streaming se gestionan dentro de sus respectivos complementos.

## Configuración

`/etc/sonora/admin.json`, propiedad de root y modo 0600:

```json
{"salt":"<al menos 16 bytes en hexadecimal>","hash":"<32 bytes en hexadecimal>","iterations":200000}
```

`hash` es PBKDF2-HMAC-SHA256 de la contraseña codificada en UTF-8. La contraseña se provisiona en el equipo; la consola no tiene una contraseña de fábrica.

`/etc/sonora/audio.json` contiene la salida y el perfil configurados:

```json
{"device":"hw:CARD=DAC,DEV=0","name":"DAC USB","mode":"pure","volume_fixed":true}
```

`/etc/sonora/player.json` identifica el reproductor local mediante su identificador SlimProto estable:

```json
{"id":"aa:bb:cc:dd:ee:ff","name":"Sonora USB"}
```

La consola selecciona la reproducción por ese identificador, incluso si hay otros reproductores Squeezelite en la red. Si falta la identidad local, no atribuye al equipo la reproducción de otro endpoint. El servicio local se comprueba como `sonora-player.service`.

`/etc/sonora/nas.json` es una lista de fuentes sin contraseñas:

```json
[{"name":"Musica","host":"192.168.1.20","share":"Music/FLAC","path":"/srv/music/nas/Musica"}]
```

El estado de montaje se obtiene del sistema, no de un valor persistido de esa lista. Los parámetros activos de audio proceden de `/proc/asound/.../hw_params`; solo se muestran cuando ALSA comunica una reproducción activa. Un perfil sin procesado no constituye por sí solo una certificación bit-perfect.

## API local

- `GET /api/status` (también `/status`): estado sin credenciales, dispositivos ALSA detectados, fuentes, biblioteca y reproductores.
- `GET /api/session`: estado de la sesión de ajustes.
- `POST /api/session` con `{"password":"..."}`: abre una sesión mediante cookie HttpOnly, SameSite=Strict y token CSRF.
- `POST /api/audio` con `{"device":"hw:CARD=DAC,DEV=0"}`: selecciona un dispositivo que figure en la detección actual.
- `POST /api/profile` con `{"mode":"pure"}` o `{"mode":"listening"}`: cambia el perfil.
- `POST /api/nas`: recibe `name`, `host`, `share` y, opcionalmente, `username`, `password`, `domain`.
- `POST /api/rescan` con `{}`: solicita un reescaneo a Lyrion.
- `POST /api/logout` con `{}`: revoca la sesión.

Las mutaciones requieren un encabezado `Origin` igual al origen de la consola, la cookie de sesión y `X-Sonora-CSRF`. El cuerpo máximo es 16 KB. Los comandos del sistema se ejecutan mediante listas de argumentos y sin shell. La contraseña SMB viaja en un JSON por stdin a `sonoractl nas-add`; no forma parte de la línea de comandos. Los errores del helper no se retransmiten al navegador para evitar revelar credenciales.

## Contrato del helper

```text
sonoractl audio --device ID
sonoractl profile --mode pure|listening
sonoractl nas-add --name NAME --host HOST --share SHARE --username USER --domain DOMAIN
```

En `nas-add`, stdin recibe `{"password":"..."}` y se cierra. La operación tiene un plazo de 75 segundos en la consola. Un código de salida distinto de cero se trata como error.

## Comprobaciones

```sh
python3 -m unittest discover -s app/tests -v
node --check app/static/app.js
```

Los tests de autenticación generan sus credenciales temporales y cierran su servidor de prueba. No requieren modificar el equipo de audio.
