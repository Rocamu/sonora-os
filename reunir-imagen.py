#!/usr/bin/env python3
"""Reunir y verificar las partes descargadas de Sonora OS, sin sobrescribir archivos."""
import hashlib,json,pathlib,sys
folder=pathlib.Path(__file__).resolve().parent
manifest=json.loads((folder/'parts-manifest.json').read_text())
target=folder/manifest['file']; temp=folder/(manifest['file']+'.incomplete')
if target.exists() or temp.exists():
 sys.exit('Ya existe el destino o un archivo .incomplete. Revísalo antes de continuar.')
for item in manifest['parts']:
 part=folder/item['name']
 if not part.is_file() or part.stat().st_size != item['size']:
  sys.exit('Falta una parte o su tamaño es incorrecto: '+item['name'])
complete=hashlib.sha256();total=0
try:
 with temp.open('xb') as output:
  for item in manifest['parts']:
   digest=hashlib.sha256()
   with (folder/item['name']).open('rb') as source:
    while True:
     block=source.read(1024*1024)
     if not block: break
     digest.update(block);complete.update(block);output.write(block);total+=len(block)
   if digest.hexdigest()!=item['sha256']:
    raise ValueError('Parte dañada: '+item['name'])
 if total!=manifest['size'] or complete.hexdigest()!=manifest['sha256']:
  raise ValueError('El SHA-256 final no coincide.')
 temp.rename(target)
 print('Imagen completa y SHA-256 verificado: '+str(target))
except Exception:
 temp.unlink(missing_ok=True)
 raise
