# Componentes de terceros

La imagen combina componentes independientes. La licencia MIT de este repositorio cubre el código original de Sonora y su documentación; cada componente conserva sus avisos y condiciones propios.

| Componente | Versión | Fuentes y licencia |
|---|---|---|
| Debian GNU/Linux | 13, versiones en `images/*packages.tsv` | [Paquetes fuente Debian](https://sources.debian.org/); cada paquete instalado incluye sus avisos en `/usr/share/doc/PAQUETE/copyright`. |
| Lyrion Music Server | 9.1.1 | [Fuentes y licencia GPL](https://github.com/LMS-Community/slimserver/tree/9.1.1). El instalador oficial se descarga con SHA-256 fijado. |
| Squeezelite | versión Debian en inventario | [Fuentes y licencia GPL](https://github.com/ralph-irving/squeezelite); se instala desde Debian. |
| Material | 6.4.14 | [Fuentes MIT](https://github.com/CDrummond/lms-material/tree/6.4.14). Aviso MIT conservado en `overlay/usr/share/sonora/Material-LICENSE.txt`. Las bibliotecas, fuentes tipográficas y recursos incluidos conservan sus avisos propios. |
| TIDAL local | 1.9.0 | Se descarga al primer arranque desde su autor, según `plugins-lock.json`; no está incorporado a la imagen. |
| Qobuz | 3.7.3 | Se descarga al primer arranque desde su autor, según `plugins-lock.json`; no está incorporado a la imagen. |

El descargador `tools/fetch_vendor.py` verifica las distribuciones oficiales de Lyrion y Material y prepara el overlay. El repositorio no incorpora los binarios del sistema ni los recursos de Roon o Daphile.
