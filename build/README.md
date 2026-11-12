# Construcción de la imagen

El resultado es un disco GPT de 4 GiB con tres particiones: arranque BIOS, EFI FAT32 (cargadores x86_64 e IA32) y raíz Linux ext4 persistente. El archivo `.img` puede copiarse íntegramente a una unidad USB/SSD destinada al sistema. Su compresión `.img.xz` reduce el tamaño de la descarga; no cambia las particiones ni los datos al descomprimir.

La construcción requiere Docker con ejecución de contenedores `linux/amd64`, 4 GB libres de RAM para el constructor y unos 10 GB libres de disco. En equipos ARM se utiliza la emulación de procesos de Docker. Todas las herramientas de Linux se instalan dentro de contenedores propios; no se instala un sistema en el equipo anfitrión.

## Etapas

Desde la raíz del proyecto, prepara primero las dependencias verificadas de sus autores y define una carpeta absoluta para las referencias:

```sh
export SONORA_REFERENCES="$PWD/vendor-cache"
python3 tools/fetch_vendor.py "$SONORA_REFERENCES"
./build/run.sh prepare
```

El descargador comprueba los SHA-256 fijados en el proyecto. Antes de finalizar deben existir `overlay/` y el paquete oficial `lyrionmusicserver_9.1.1_amd64.deb` en esa carpeta. `vendor-cache/` es también la ubicación predeterminada si no se define la variable.

Una vez completada la configuración de la aplicación:

```sh
touch overlay.ready
./build/run.sh finalize
./build/run.sh image
```

`finalize` copia la configuración y ejecuta el hook opcional `/usr/local/sbin/sonora-image-setup` dentro del sistema aislado. Las credenciales específicas del equipo se crean en el primer arranque, no durante la construcción.

`image` se niega a sobrescribir una imagen existente. Los dispositivos loop se asignan a un archivo de imagen propio, se comprueba esa correspondencia antes de formatearlos y se liberan al finalizar. No se seleccionan discos físicos.

Los archivos finales quedan en `images/`, junto con SHA-256, lista de paquetes, tabla de particiones y un manifiesto de arquitectura/kernel. Las versiones exactas instaladas quedan registradas; una reconstrucción posterior puede incorporar actualizaciones de seguridad de Debian.

Los Mac Intel con CPU de 64 bits y firmware EFI de 32 bits disponen de `BOOTIA32.EFI` y un kernel con modo EFI mixto. Esa ruta debe comprobarse en el modelo concreto. La imagen no está destinada a Apple Silicon, PowerPC ni procesadores x86 de 32 bits.

## Prueba de arranque

`test-boot.sh` usa QEMU, una capa de escritura temporal y una tarjeta de audio USB emulada. El archivo entregable permanece sin cambios. Admite `bios`, `uefi` y `secureboot`; la presencia de una cadena firmada no equivale por sí sola a una prueba de arranque seguro.

Ejemplo dentro de un contenedor Linux ARM64 preparado con `qemu-system-x86`, `qemu-utils` y `ovmf`:

```sh
./build/test-boot.sh bios /project/images/sonora-os-0.1.0-amd64.img
```

Los puertos del invitado se redirigen a 19080 (administración), 19000 (Lyrion) y 19090 (CLI Lyrion) dentro del contenedor. Para acceder desde el anfitrión deben publicarse únicamente en `127.0.0.1`. Los logs de consola pueden contener las credenciales temporales del equipo de prueba y deben conservarse fuera de entregables públicos.

Una prueba virtual comprueba arranque y servicios, pero no sustituye la comprobación de un DAC USB físico, sus frecuencias, un NAS y las cuentas de streaming.

## Pruebas de audio y persistencia

Las variables opcionales `SONORA_TEST_USB_MUSIC` y `SONORA_TEST_AUDIO_WAV` conectan un archivo de disco USB sintético y una captura WAV de salida. `make-test-usb.sh` crea un archivo nuevo de 128 MiB con partición FAT32 y los WAV de prueba indicados; se niega a sobrescribir un archivo existente. Esos medios no forman parte de la imagen de producción.

La tarjeta USB emulada de QEMU usa PCM de 48 kHz. La captura predeterminada es 48 kHz, 16 bits y dos canales. Una prueba con otra frecuencia puede incluir conversión del dispositivo emulado. El mezclador USB virtual también debe verificarse antes de comparar las muestras; su valor inicial no tiene por qué ser unidad.

`SONORA_TEST_ALLOW_REBOOT=1` permite reiniciar el invitado manteniendo la misma capa de escritura. El harness se niega a reemplazar una capa existente; `SONORA_TEST_REUSE_OVERLAY=1` permite reutilizarla explícitamente. La consola interactiva privada queda en `/tmp/sonora-serial.sock` dentro del contenedor y QMP en `/tmp/sonora-qmp.sock`.

`poweroff-test.py` solicita un apagado normal mediante ACPI. Hay que esperar la terminación de QEMU antes de retirar el contenedor. Las capturas y los resultados de pruebas se conservan fuera de `images/`.
