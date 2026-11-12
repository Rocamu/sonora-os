#!/usr/bin/env python3
"""Fixed, validated operating-system operations for the Sonora audio appliance."""
import argparse, fcntl, hashlib, ipaddress, json, os, pathlib, pwd, re, secrets, shutil, subprocess, sys, tempfile, urllib.request
ROOT = pathlib.Path(os.environ.get('SONORA_TEST_ROOT', '/'))
def path(s): return ROOT / s.lstrip('/')
def read_json(p, default=None):
    try: return json.loads(path(p).read_text())
    except (OSError, ValueError): return default

def atomic(p, data, mode=0o644):
    p = path(p); p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.sonora-', dir=p.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def save(p, obj, mode=0o644): atomic(p, json.dumps(obj, ensure_ascii=False, indent=2)+'\n', mode)
def run(argv, timeout=30):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env={**os.environ,'LC_ALL':'C'})
    if r.returncode: raise RuntimeError('No se pudo completar '+pathlib.Path(argv[0]).name+' (código '+str(r.returncode)+'). Consulta el registro local del servicio.')
    return r.stdout

def require_root():
    if os.geteuid()!=0: raise PermissionError('Esta operación requiere administración local del sistema.')
def slug(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', value): raise ValueError('Nombre: 1–32 letras, números, guiones o guion bajo.')
    return value

def hostname(value):
    if len(value)>253 or not value or any(c.isspace()for c in value): raise ValueError('Dirección de servidor inválida.')
    try: ipaddress.ip_address(value); return value
    except ValueError: pass
    if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',x)for x in value.rstrip('.').split('.')): raise ValueError('Servidor: usa una IP o un nombre DNS sin barras.')
    return value

def share_path(value):
    if not value or len(value)>256 or any(c in value for c in '\r\n\x00\\,%') or value.startswith('/') or any(x in ('','..','.')for x in value.split('/')): raise ValueError('Carpeta compartida inválida; usa Compartida/subcarpeta.')
    return value

def credential(value):
    if not isinstance(value,str)or len(value)>1024 or any(c in value for c in '\r\n\x00'): raise ValueError('Credencial inválida.')
    return value

def rpc(command, player=''):
    req=urllib.request.Request('http://127.0.0.1:9000/jsonrpc.js',data=json.dumps({'id':1,'method':'slim.request','params':[player,command]}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=5)as res: result=json.load(res)
    if result.get('error'): raise RuntimeError('Lyrion no pudo completar el comando.')
    return result.get('result',{})

def devices():
    try: text=run(['/usr/bin/aplay','-l'],10)
    except (OSError,RuntimeError): return []
    result=[]
    for line in text.splitlines():
        m=re.match(r'^card\s+(\d+):\s+([A-Za-z0-9_-]+)\s+\[(.*?)\],\s+device\s+(\d+):\s+(.*?)\s+\[',line)
        if not m: continue
        card, ident, name, dev, desc=m.groups()
        result.append({'device':f'hw:CARD={ident},DEV={dev}','name':f'{name} · {desc}','card':int(card),'pcm':int(dev),'usb':path(f'/proc/asound/card{card}/stream0').exists()or'/usb'in str(path(f'/sys/class/sound/card{card}/device').resolve())})
    return result

def audio(device):
    require_root()
    if not re.fullmatch(r'hw:CARD=[A-Za-z0-9_-]{1,64},DEV=\d{1,2}',device): raise ValueError('Selecciona una salida ALSA hw válida.')
    match=next((d for d in devices()if d['device']==device),None)
    if not match: raise ValueError('La salida ya no está conectada.')
    run(['systemctl','stop','sonora-player.service'])
    old=read_json('/etc/sonora/audio.json',{})
    cfg={**old,'device':device,'name':match['name'],'usb':match['usb'],'mode':old.get('mode','pure'),'volume_fixed':old.get('mode','pure')=='pure'}
    save('/etc/sonora/audio.json',cfg)
    run(['systemctl','start','sonora-player.service'])
    return cfg

def profile(mode):
    require_root()
    if mode not in ('pure','listening'): raise ValueError('Perfil no reconocido.')
    player=read_json('/etc/sonora/player.json',{}).get('id')
    if player:
        try: rpc(['stop'],player)
        except (OSError,RuntimeError): pass
    cfg=read_json('/etc/sonora/audio.json',{'device':None})
    cfg.update(mode=mode,volume_fixed=mode=='pure');save('/etc/sonora/audio.json',cfg)
    # The LMS Sonora plugin observes this file and applies the matching preferences.
    # Never resume playback or raise ALSA hardware volume here.
    return cfg

def nas_add(name,host,share,username='',domain='',password=''):
    require_root();slug(name);hostname(host);share_path(share)
    for v in (username,domain,password):credential(v)
    records=read_json('/etc/sonora/nas.json',[])
    if not isinstance(records,list):raise ValueError('Configuración NAS inválida.')
    if any(x.get('name')==name for x in records):raise ValueError('Ya existe una fuente con ese nombre.')
    mountpoint='/srv/music/nas/'+name
    path(mountpoint).mkdir(parents=True,exist_ok=True)
    if path(mountpoint).is_symlink()or any(path(mountpoint).iterdir()):raise ValueError('La carpeta destino debe estar vacía.')
    creds='/etc/sonora/credentials/'+name
    if path(creds).exists():raise ValueError('Ya existe una configuración para ese nombre.')
    path('/etc/sonora/credentials').mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(path('/etc/sonora/credentials'),0o700)
    atomic(creds,f'username={username}\npassword={password}\ndomain={domain}\n',0o600)
    user=pwd.getpwnam('squeezeboxserver')
    opts=f'credentials={creds},vers=default,ro,nosuid,nodev,noexec,uid={user.pw_uid},gid={user.pw_gid},iocharset=utf8,_netdev'
    if not username:opts+=',guest'
    unit=run(['systemd-escape','--path','--suffix=mount',mountpoint]).strip()
    auto=unit.removesuffix('.mount')+'.automount'
    try:
        atomic('/etc/systemd/system/'+unit,'[Unit]\nDescription=Sonora NAS '+name+'\nWants=network-online.target\nAfter=network-online.target\n\n[Mount]\nWhat=//'+host.replace('%','%%')+'/'+share.replace('%','%%')+'\nWhere='+mountpoint+'\nType=cifs\nOptions='+opts+'\nTimeoutSec=30\n')
        atomic('/etc/systemd/system/'+auto,'[Unit]\nDescription=Sonora NAS '+name+'\n\n[Automount]\nWhere='+mountpoint+'\nTimeoutIdleSec=300\n\n[Install]\nWantedBy=multi-user.target\n')
        # PID 1 mounts it in the host namespace; the web service has no mount capability.
        run(['systemctl','daemon-reload']);run(['systemctl','start',unit],40);run(['systemctl','enable',auto])
        records.append({'name':name,'host':host,'share':share,'path':mountpoint,'read_only':True})
        save('/etc/sonora/nas.json',records)
        try:rpc(['rescan'])
        except (OSError,RuntimeError):pass
        return {'name':name,'path':mountpoint,'read_only':True}
    except Exception:
        if not os.path.ismount(path(mountpoint)):
            path(creds).unlink(missing_ok=True)
            for item in (unit,auto):path('/etc/systemd/system/'+item).unlink(missing_ok=True)
        raise

def usb_mount(device):
    require_root()
    if not re.fullmatch(r'/dev/(sd[a-z]+\d+|nvme\d+n\d+p\d+)',device):raise ValueError('Partición USB no válida.')
    info=json.loads(run(['lsblk','--json','--paths','--output','NAME,TYPE,FSTYPE,UUID,TRAN,MOUNTPOINTS',device]))['blockdevices'][0]
    if info.get('type')!='part'or any(info.get('mountpoints')or[]):return {'skipped':'La partición ya está montada o no es una partición.'}
    ancestry=run(['lsblk','--noheadings','--inverse','--output','TRAN',device]).split()
    if 'usb'not in ancestry:raise ValueError('El disco no está conectado por USB.')
    fs=info.get('fstype');uuid=info.get('uuid','')
    if fs not in ('ext4','ext3','ext2','vfat','exfat','ntfs','ntfs3')or not re.fullmatch(r'[A-Fa-f0-9-]{4,64}',uuid):raise ValueError('Formato o identificador de disco no admitido.')
    target='/srv/music/usb/'+uuid
    path(target).mkdir(parents=True,exist_ok=True)
    opts='ro,nodev,nosuid,noexec'
    if fs in ('vfat','exfat','ntfs','ntfs3'):
        u=pwd.getpwnam('squeezeboxserver');opts+=f',uid={u.pw_uid},gid={u.pw_gid},dmask=0022,fmask=0133'
    run(['mount','-o',opts,device,target],30)
    try:rpc(['rescan'])
    except (OSError,RuntimeError):pass
    return {'path':target,'read_only':True}

def grow_root():
    require_root()
    root = run(['findmnt','--noheadings','--output','SOURCE','/']).strip()
    if not re.fullmatch(r'/dev/(sd[a-z]+\d+|vd[a-z]+\d+|nvme\d+n\d+p\d+|mmcblk\d+p\d+)',root):raise ValueError('No se reconoce la partición raíz.')
    if run(['blkid','-s','LABEL','-o','value',root]).strip()!='SONORA_ROOT':raise ValueError('La raíz no tiene la etiqueta de Sonora.')
    block=pathlib.Path(root).name
    number=path('/sys/class/block/'+block+'/partition').read_text().strip()
    disk=run(['lsblk','--noheadings','--output','PKNAME',root]).strip()
    if number!='3' or not re.fullmatch(r'(sd[a-z]+|vd[a-z]+|nvme\d+n\d+|mmcblk\d+)',disk):raise ValueError('Esquema de arranque no reconocido.')
    result=subprocess.run(['growpart','/dev/'+disk,number],capture_output=True,text=True,timeout=30)
    if result.returncode not in (0,1):raise RuntimeError('No se pudo ampliar la partición raíz.')
    run(['resize2fs',root],90)
    return {'root':root,'expanded':result.returncode==0}

def firstboot():
    require_root()
    etc=path('/etc/sonora');etc.mkdir(parents=True,exist_ok=True)
    if not path('/etc/sonora/admin.json').exists():
        password=secrets.token_urlsafe(12);salt=secrets.token_bytes(24);iterations=200000
        digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations).hex()
        save('/etc/sonora/admin.json',{'salt':salt.hex(),'hash':digest,'iterations':iterations},0o600)
        # A unique local-console password; SSH is not installed or enabled.
        subprocess.run(['/usr/sbin/chpasswd'],input='root:'+password+'\n',text=True,check=True,capture_output=True)
        atomic('/etc/sonora/first-access.txt','SONORA OS\n\nPanel: http://sonora.local/\nBiblioteca: http://sonora.local:9000/material/\nContraseña del panel y consola local (root): '+password+'\n\nControla el nivel en tu DAC o amplificador al usar Pure.\nEsta contraseña solo se muestra en la consola local.\n',0o600)
    if not path('/etc/sonora/player.json').exists():
        mid=path('/etc/machine-id').read_text().strip()
        mac=bytearray(hashlib.sha256(mid.encode()).digest()[:6]);mac[0]=(mac[0]|2)&254
        save('/etc/sonora/player.json',{'id':':'.join(f'{b:02x}'for b in mac),'name':'Sonora USB'})
    if not path('/etc/sonora/audio.json').exists():save('/etc/sonora/audio.json',{'device':None,'mode':'pure','volume_fixed':True})
    if not path('/etc/sonora/nas.json').exists():save('/etc/sonora/nas.json',[])
    return {'ready':True}

def player():
    cfg=read_json('/etc/sonora/audio.json',{})
    device=cfg.get('device');items=devices()
    if not device:
        usb=next((x for x in items if x['usb']),None)
        if not usb:
            print('No hay DAC USB conectado. Conéctalo y selecciona su salida en Sonora.',file=sys.stderr);return 75
        # Initial USB discovery only; never switch away from a previously selected DAC.
        device=usb['device'];save('/etc/sonora/audio.json',{**cfg,**{k:usb[k]for k in ['device','name','usb']}})
    if device not in [d['device']for d in items]:
        print('El DAC seleccionado no está conectado. No se usará otra salida.',file=sys.stderr);return 75
    identity=read_json('/etc/sonora/player.json',{})
    argv=['/usr/bin/squeezelite','-n',identity.get('name','Sonora USB'),'-m',identity['id'],'-M','Sonora','-s','127.0.0.1','-o',device,'-b','4096:4096','-a','80:4::1','-C','10']
    user=pwd.getpwnam('sonora-player')
    os.setgroups([pwd.getpwnam('sonora-player').pw_gid, __import__('grp').getgrnam('audio').gr_gid])
    os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    os.execv(argv[0],argv)

def main(argv=None):
    ap=argparse.ArgumentParser(description='Administración local de Sonora OS');sub=ap.add_subparsers(dest='command',required=True)
    a=sub.add_parser('audio');a.add_argument('--device',required=True)
    a=sub.add_parser('profile');a.add_argument('--mode',choices=['pure','listening'],required=True)
    a=sub.add_parser('nas-add');a.add_argument('--name',required=True);a.add_argument('--host',required=True);a.add_argument('--share',required=True);a.add_argument('--username',default='');a.add_argument('--domain',default='')
    a=sub.add_parser('usb-mount');a.add_argument('--device',required=True)
    for name in ['firstboot','player','devices','grow-root']:sub.add_parser(name)
    args=ap.parse_args(argv)
    try:
        if args.command not in ('devices','player'):
            path('/run').mkdir(parents=True,exist_ok=True)
            lock=open(path('/run/sonora-control.lock'),'a')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Hay otra operación de Sonora en curso.')
        if args.command=='devices':result=devices()
        elif args.command=='audio':result=audio(args.device)
        elif args.command=='profile':result=profile(args.mode)
        elif args.command=='nas-add':
            raw=sys.stdin.read(4097)
            if len(raw)>4096:raise ValueError('Credencial demasiado larga.')
            obj=json.loads(raw or '{}')
            if not isinstance(obj,dict)or set(obj)-{'password'}:raise ValueError('Formato de credenciales inválido.')
            result=nas_add(args.name,args.host,args.share,args.username,args.domain,obj.get('password',''))
        elif args.command=='usb-mount':result=usb_mount(args.device)
        elif args.command=='firstboot':result=firstboot()
        elif args.command=='grow-root':result=grow_root()
        elif args.command=='player':return player()
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False));return 0
    except Exception as e:
        # Error messages never include command stderr, tokens, or NAS passwords.
        print(json.dumps({'ok':False,'error':str(e)if isinstance(e,(ValueError,PermissionError,RuntimeError))else 'No se pudo completar la operación.'},ensure_ascii=False));return 1
if __name__=='__main__':sys.exit(main())
