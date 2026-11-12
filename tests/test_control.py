import importlib.util,json,pathlib,tempfile,types,unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('sonora_control',pathlib.Path(__file__).resolve().parents[1]/'overlay/usr/local/lib/sonora/control.py')
c=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(c)
class ControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.original=c.ROOT;c.ROOT=self.root
 def tearDown(self):c.ROOT=self.original;self.tmp.cleanup()
 def test_bad_servers_rejected(self):
  for s in ['-o credentials=x','host/share','x;id','a\nb','..','']:
   with self.subTest(s=s),self.assertRaises(ValueError):c.hostname(s)
 def test_valid_servers(self):
  for s in ['192.168.1.2','music-nas.local','NAS']:self.assertEqual(c.hostname(s),s)
 def test_share_traversal_and_unit_injection_rejected(self):
  for s in ['../music','foo/../bar','/root','music\nWhat=/dev/sda','music,%x','music\\foo']:
   with self.subTest(s=s),self.assertRaises(ValueError):c.share_path(s)
 def test_space_in_share_is_valid(self):self.assertEqual(c.share_path('Music Library/FLAC'),'Music Library/FLAC')
 def test_credentials_reject_newlines(self):
  for s in ['hello\nusername=root','p\rword','a\x00b']:
   with self.assertRaises(ValueError):c.credential(s)
 def test_atomic_json_permissions(self):
  c.save('/etc/sonora/x.json',{'ok':True},0o600);p=self.root/'etc/sonora/x.json';self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(p.read_text()),{'ok':True})
 def test_audio_injection_rejected_before_system_commands(self):
  with patch.object(c,'require_root'),patch.object(c,'run')as call:
   with self.assertRaises(ValueError):c.audio('hw:CARD=USB;reboot,DEV=0')
   call.assert_not_called()
 def test_audio_disconnected_rejected(self):
  with patch.object(c,'require_root'),patch.object(c,'devices',return_value=[]),patch.object(c,'run')as call:
   with self.assertRaises(ValueError):c.audio('hw:CARD=USB,DEV=0')
   call.assert_not_called()
 def test_audio_switch_stops_before_changes_then_starts(self):
  d={'device':'hw:CARD=USB,DEV=0','name':'Test USB','usb':True};calls=[]
  with patch.object(c,'require_root'),patch.object(c,'devices',return_value=[d]),patch.object(c,'run',side_effect=lambda args,*a:calls.append(args)or''):
   self.assertEqual(c.audio(d['device'])['mode'],'pure')
  self.assertEqual(calls,[['systemctl','stop','sonora-player.service'],['systemctl','start','sonora-player.service']])
 def test_profile_never_autoplays(self):
  c.save('/etc/sonora/player.json',{'id':'02:00:00:00:00:01'});c.save('/etc/sonora/audio.json',{'device':'hw:CARD=USB,DEV=0','mode':'pure'})
  with patch.object(c,'require_root'),patch.object(c,'rpc',return_value={})as rpc:
   cfg=c.profile('listening')
  self.assertFalse(cfg['volume_fixed']);rpc.assert_called_once_with(['stop'],'02:00:00:00:00:01')
 def test_profile_rejects_unknown_mode(self):
  with patch.object(c,'require_root'),self.assertRaises(ValueError):c.profile('arbitrary')
 def test_nas_secret_in_file_not_argv_or_public_json(self):
  calls=[];u=types.SimpleNamespace(pw_uid=123,pw_gid=124)
  def run(args,*_):calls.append(args);return 'srv-music-nas-Library.mount\n'if args[0]=='systemd-escape'else''
  with patch.object(c,'require_root'),patch.object(c.pwd,'getpwnam',return_value=u),patch.object(c,'run',side_effect=run),patch.object(c,'rpc',return_value={}):
   result=c.nas_add('Library','192.168.1.2','My Music','reader','','special$pass,word')
  self.assertNotIn('special$pass',json.dumps(calls));self.assertNotIn('special$pass',(self.root/'etc/sonora/nas.json').read_text());self.assertEqual((self.root/'etc/sonora/credentials/Library').stat().st_mode&0o777,0o600);self.assertTrue(result['read_only']);self.assertIn('vers=default',(self.root/'etc/systemd/system/srv-music-nas-Library.mount').read_text());self.assertIn(['systemctl','start','srv-music-nas-Library.mount'],calls)
 def test_nas_invalid_name_does_not_create_secret(self):
  with patch.object(c,'require_root'),self.assertRaises(ValueError):c.nas_add('../../evil','host','music',password='password')
  self.assertFalse((self.root/'etc/sonora/credentials').exists())
 def test_duplicate_nas_is_preserved(self):
  c.save('/etc/sonora/nas.json',[{'name':'Library'}])
  with patch.object(c,'require_root'),self.assertRaises(ValueError):c.nas_add('Library','host','share')
 def test_root_disk_not_usb_remounted(self):
  info={'blockdevices':[{'type':'part','mountpoints':['/'],'fstype':'ext4','uuid':'1234'}]}
  with patch.object(c,'require_root'),patch.object(c,'run',return_value=json.dumps(info))as run:
   self.assertIn('skipped',c.usb_mount('/dev/sda3'))
  self.assertEqual(run.call_count,1)
 def test_arbitrary_device_rejected(self):
  with patch.object(c,'require_root'),patch.object(c,'run')as run,self.assertRaises(ValueError):c.usb_mount('/dev/sda1;reboot')
  run.assert_not_called()
 def test_firstboot_unique_credentials_and_idempotency(self):
  c.path('/etc').mkdir();c.path('/etc/machine-id').write_text('fixture-one')
  with patch.object(c,'require_root'),patch.object(c.subprocess,'run')as run:
   c.firstboot();before=c.read_json('/etc/sonora/admin.json');identity=c.read_json('/etc/sonora/player.json');c.firstboot()
  self.assertEqual(before,c.read_json('/etc/sonora/admin.json'));self.assertEqual(run.call_count,1);self.assertEqual(int(identity['id'].split(':')[0],16)&3,2);self.assertEqual(c.path('/etc/sonora/first-access.txt').stat().st_mode&0o777,0o600)
 def test_grow_refuses_unknown_boot_filesystem(self):
  with patch.object(c,'require_root'),patch.object(c,'run',side_effect=['/dev/sda3\n','OTHER_SYSTEM\n'])as run,self.assertRaises(ValueError):c.grow_root()
  self.assertFalse(any(x.args[0][0]=='growpart'for x in run.call_args_list))
if __name__=='__main__':unittest.main()
