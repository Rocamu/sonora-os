#!/usr/bin/env python3
"""Fetch build inputs from their publishers and verify pinned SHA-256 values."""
import hashlib,pathlib,sys,urllib.request,zipfile
folder=pathlib.Path(sys.argv[1]if len(sys.argv)>1 else'vendor-cache').resolve();folder.mkdir(parents=True,exist_ok=True)
items=[('lyrionmusicserver_9.1.1_amd64.deb','https://downloads.lms-community.org/LyrionMusicServer_v9.1.1/lyrionmusicserver_9.1.1_amd64.deb','7688f24650bc8edeeafc80aa34d5f7bf980ff105f4a8edc149c84c5ac8b26989'),('lms-material-6.4.14.zip','https://github.com/CDrummond/lms-material/releases/download/6.4.14/lms-material-6.4.14.zip','aba5aa0c7141862b5f3d5aad8e8833c8e1810b2fea39a6add20470329f9fd735')]
for name,url,digest in items:
 target=folder/name
 if target.exists()and hashlib.sha256(target.read_bytes()).hexdigest()==digest:print(name+': verificado');continue
 temp=folder/(name+'.part')
 try:
  with urllib.request.urlopen(url,timeout=60)as res,open(temp,'wb')as out:
   total=0
   while True:
    chunk=res.read(1024*1024)
    if not chunk:break
    total+=len(chunk)
    if total>40_000_000:raise ValueError('Descarga superior al tamaño previsto.')
    out.write(chunk)
  if hashlib.sha256(temp.read_bytes()).hexdigest()!=digest:raise ValueError('No coincide el SHA-256 de '+name)
  temp.replace(target);print(name+': descargado y verificado')
 finally:temp.unlink(missing_ok=True)

# Populate the overlay from the verified official release.
material=pathlib.Path(__file__).resolve().parents[1]/'overlay/usr/share/squeezeboxserver/Plugins/MaterialSkin'
material.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(folder/'lms-material-6.4.14.zip') as archive:
 for entry in archive.infolist():
  target=(material/entry.filename).resolve()
  if not target.is_relative_to(material.resolve()):
   raise ValueError('Unsafe archive path: '+entry.filename)
 archive.extractall(material)
print('Material 6.4.14: instalado en overlay')
