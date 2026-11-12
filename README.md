# Sonora OS 0.1.0

Sonora es un sistema Linux de audio para mini PC Intel/AMD de 64 bits y Mac Intel compatibles. La música se reproduce en el equipo conectado al DAC USB; el navegador o iPeng actúan como mando a distancia.

El sistema combina Debian 13, Lyrion Music Server 9.1.1, Squeezelite, ALSA, Material y una consola Sonora. El archivo de disco de 4 GiB incluye arranque BIOS, EFI de 64 bits, cargador EFI de 32 bits para CPU compatibles y raíz ext4 persistente.

## Descargas

[Imagen, SHA-256 y guía de instalación en Google Drive](https://drive.google.com/drive/folders/15KFt2aeeiXA5gwjzyuEgbjaQibcRhRVy). La imagen de disco se distribuye por separado del código.

## Empezar

1. Usa `images/sonora-os-0.1.0-amd64.img.xz` y su archivo SHA-256. La imagen descomprimida termina en `.img`.
2. Graba la imagen completa en una unidad USB o SSD destinada a Sonora, de al menos 8 GB. **La grabación reemplaza el contenido del dispositivo seleccionado.** No basta copiar el archivo a una carpeta del USB. Una herramienta de grabación de imágenes puede descomprimir XZ; si no lo admite, descomprime primero.
3. Conecta Ethernet, el DAC USB y, si corresponde, una unidad con música. Arranca el mini PC desde la unidad Sonora. En un Mac Intel, usa su selector de disco de arranque. La posibilidad de arrancar depende del modelo y de su firmware.
4. En el primer arranque, una pantalla conectada muestra la dirección del equipo y una contraseña única para ajustes y consola local. Consérvala. Después de la configuración puedes retirar pantalla y teclado.
5. Desde otro dispositivo de la misma red abre `http://sonora.local/`. Si el nombre no se resuelve, usa la IP de Sonora que muestre el router o la pantalla del equipo.
6. Pulsa **Abrir biblioteca** para acceder a Material. La dirección directa es `http://sonora.local:9000/material/`.

El primer DAC USB disponible puede seleccionarse al arrancar. Una salida elegida queda guardada; si desaparece, el reproductor no cambia automáticamente a otra. La reproducción no comienza por sí sola.

## Música local y NAS

Una unidad USB particionada con un sistema de archivos compatible se monta automáticamente en modo de solo lectura bajo `/srv/music/usb`. Se admiten ext4, FAT, exFAT y NTFS, sujeto a permisos del contenido. La unidad de arranque ya montada no se incorpora como biblioteca USB.

En **Fuentes musicales → Añadir carpeta del NAS**, introduce el nombre, dirección del servidor y carpeta SMB. Por ejemplo, `Musica` o `Musica/FLAC`. Las credenciales se guardan en un archivo local de administración con permisos restringidos. El montaje es de solo lectura y negocia un dialecto SMB moderno compatible con el servidor.

La biblioteca abarca `/srv/music`. Las canciones, favoritos, playlists, configuración y base de datos se conservan en la raíz persistente. También existe `/srv/music/local` para una colección copiada al almacenamiento del sistema.

## Pure y Escucha

**Pure** utiliza el dispositivo ALSA `hw` seleccionado, volumen digital fijo, ReplayGain desactivado y sin crossfade ni remuestreo forzado. **Baja el nivel y controla el volumen en el DAC o amplificador antes de reproducir.** El formato original debe ser compatible con el DAC. Esta modalidad se orienta a PCM; la conversión de formatos como DSD a PCM no representa una ruta intacta.

**Escucha** habilita el control de volumen digital de Lyrion. Sus preferencias de normalización se pueden configurar desde el servidor. Cambiar de perfil detiene la música y no la reanuda automáticamente.

La ruta de señal muestra datos de fuente y parámetros ALSA cuando están disponibles. «Pure» identifica una configuración; no certifica por sí mismo la igualdad de muestras dentro de cualquier DAC.

## TIDAL y Qobuz

El primer arranque intenta obtener los complementos TIDAL local y Qobuz desde las distribuciones de sus autores, comprobando sus SHA-256. La música local funciona sin cuentas de streaming. Si no hay conexión a Internet, los complementos pueden instalarse posteriormente desde **Ajustes → Plugins** de Lyrion; también se puede ejecutar `systemctl start sonora-plugins` desde la consola local y reiniciar Lyrion después de instalar.

Desde el acceso de cada servicio en Sonora abre sus ajustes de Lyrion, selecciona el complemento correspondiente e introduce allí tu cuenta. TIDAL utiliza el flujo de autorización del servicio; Qobuz ofrece sus campos de acceso en el complemento. Se requieren suscripciones compatibles. Las credenciales no se introducen en archivos de código ni en el chat.

La disponibilidad del catálogo y su calidad dependen de la cuenta, el país, el servicio y el complemento. Esta integración no es TIDAL Connect ni Roon Ready.

## iPeng y otras aplicaciones LMS

Conecta el teléfono o iPad a la misma LAN. En iPeng selecciona el servidor **Sonora** y el reproductor **Sonora USB**. Si no aparece, configura manualmente la IP de Sonora y el puerto 9000. Una red de invitados o una separación entre redes puede impedir el descubrimiento.

El servidor conserva los protocolos nativos de LMS: HTTP 9000, CLI 9090 y Slimproto 3483 TCP/UDP. La función adicional Playback de iPeng sirve para reproducir en el teléfono; no hace falta para controlar el DAC conectado al mini PC.

## Almacenamiento y administración

La imagen crea una raíz de unos 4 GB, incluso si la unidad física es mayor. Para aprovechar el espacio restante del soporte de Sonora, entra en su consola local como `root`, usando la contraseña del primer arranque, y ejecuta:

```sh
sonoractl grow-root
```

El comando identifica la partición actualmente montada como `/`, exige la etiqueta `SONORA_ROOT` y amplía únicamente esa partición del soporte de Sonora. No recibe un disco arbitrario como argumento. Es recomendable realizar esta operación antes de copiar una biblioteca extensa.

La consola web se sirve por HTTP en la red local. Utilízala en una LAN de confianza y no publiques sus puertos en Internet. SSH no está instalado ni habilitado. Conserva una copia independiente de tu colección musical; la raíz persistente no sustituye un respaldo.

Para un apagado normal desde la consola local:

```sh
poweroff
```

## Compatibilidad prevista

- Mini PC x86_64 con Ethernet y USB Audio Class: Intel N100/N150 y plataformas Intel/AMD equivalentes son candidatos de bajo coste.
- Mac Intel con CPU de 64 bits: el arranque y los controladores deben comprobarse en el modelo concreto. Se incluye cargador IA32 para algunos equipos con EFI de 32 bits y CPU de 64 bits.
- La imagen no está destinada a Apple Silicon, PowerPC ni CPU x86 de 32 bits.
- Ethernet es la conexión inicial recomendada. La compatibilidad Wi-Fi depende del adaptador y no dispone de un asistente gráfico en esta edición.
- Las frecuencias y formatos USB admitidos dependen del DAC. La imagen no sustituye una certificación de hardware.

## Código y construcción

`app/` contiene la consola web y sus tests; `overlay/` contiene servicios y configuración del sistema; `build/` contiene el constructor de disco; `tools/` obtiene entradas verificadas.

```sh
export SONORA_REFERENCES="$PWD/vendor-cache"
python3 tools/fetch_vendor.py "$SONORA_REFERENCES"
./build/run.sh prepare
touch overlay.ready
./build/run.sh finalize
./build/run.sh image
```

La construcción requiere Docker con contenedores Linux amd64, unos 4 GB de RAM disponibles y espacio temporal suficiente. Solo se crean archivos de imagen y dispositivos loop asociados a ellos dentro del entorno de construcción. Consulta `build/README.md` para parámetros y pruebas de arranque.

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s app/tests -v
```

Los paquetes de Debian, Lyrion, Squeezelite, Material y los complementos conservan sus respectivas condiciones. La imagen incluye la lista de paquetes y sus versiones. Material y Lyrion tienen fuentes públicas; los complementos de servicios se obtienen de sus autores al instalarse. Sonora no contiene software ni recursos propietarios copiados de Daphile o Roon.

Fuentes de componentes: [Lyrion](https://github.com/LMS-Community/slimserver), [Squeezelite](https://github.com/ralph-irving/squeezelite), [Material](https://github.com/CDrummond/lms-material), [Debian](https://sources.debian.org/).

El diseño funcional y las fuentes de referencia están en `docs/diseno.html`.
