import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class ValidationTests(unittest.TestCase):
    def test_valid_share_keeps_password_as_data(self):
        data = server.validate_nas({'name':'Jazz','host':'nas.local','share':'Musica/FLAC','username':'listener','password':'abc $() ; | %'})
        self.assertEqual(data['password'], 'abc $() ; | %')

    def test_path_and_host_injection_rejected(self):
        for field, values in {
            'name':['../tmp','a b','x;id','-flag/xx','x'*33],
            'host':['$(id)','nas/a','nas;id','a..b','-host','http://nas','nas\n.local'],
            'share':['/Music','../Music','Music/../private','Music//Jazz','Music\\Jazz','Music\x00']}.items():
            for value in values:
                data={'name':'Music','host':'nas.local','share':'Music',field:value}
                with self.subTest(field=field,value=value), self.assertRaises(server.APIError):
                    server.validate_nas(data)

    def test_unknown_json_fields_and_nonstring_fields_rejected(self):
        for value in [{'name':'M','host':'n','share':'M','command':'reboot'}, {'name':'M','host':'n','share':[]}, []]:
            with self.assertRaises(server.APIError): server.validate_nas(value)

    def test_ipv4_and_ipv6_addresses_accepted(self):
        for host in ['192.168.1.10','fd00::1234']:
            self.assertEqual(server.validate_nas({'name':'Music','host':host,'share':'Music'})['host'],host)

    def test_status_never_returns_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'nas.json').write_text(json.dumps([{'name':'M','host':'n','share':'M','username':'private','password':'secret','token':'secret-token','path':'/srv/music/nas/M'}]))
            result=server.safe_sources(path)
            self.assertNotIn('secret',json.dumps(result))
            self.assertNotIn('username',result[0])

    def test_service_and_player_identity_follow_local_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'player.json').write_text(json.dumps({'id':'AA:BB:CC:DD:EE:FF','name':'Sonora USB'}))
            context=server.Context(root)
            inventory={'players_loop':[{'playerid':'11:22:33:44:55:66','name':'Otro cuarto','model':'squeezelite'},
                                       {'playerid':'aa:bb:cc:dd:ee:ff','name':'Sonora USB','model':'squeezelite'}]}
            state={'mode':'play','playlist_loop':[{'title':'Pista real','samplerate':96000,'samplesize':24,'type':'flc','url':'https://service/secret-token'}]}
            with patch.object(server,'audio_devices',return_value=[]),patch.object(server,'read_hw_params',return_value=[]),patch.object(server,'command',return_value=SimpleNamespace(stdout='active\n')) as command,patch.object(server,'lms_request',side_effect=[inventory,state]) as rpc:
                result=context.status()
            self.assertTrue(result['services']['squeezelite'])
            self.assertIn(unittest.mock.call(['/usr/bin/systemctl','is-active','sonora-player.service'],2),command.call_args_list)
            self.assertEqual(rpc.call_args_list[-1],unittest.mock.call(['status','-','1','tags:aldorTIH'],'aa:bb:cc:dd:ee:ff'))
            self.assertEqual(result['track']['samplerate'],96000)
            self.assertEqual(result['track']['sample_size'],24)
            self.assertNotIn('url',result['track'])
            self.assertNotIn('secret-token',json.dumps(result))

    def test_absent_local_identity_does_not_select_a_remote_player(self):
        with tempfile.TemporaryDirectory() as directory:
            context=server.Context(Path(directory))
            inventory={'players_loop':[{'playerid':'11:22:33:44:55:66','name':'Otro cuarto','model':'squeezelite'}]}
            with patch.object(server,'audio_devices',return_value=[]),patch.object(server,'read_hw_params',return_value=[]),patch.object(server,'command',return_value=SimpleNamespace(stdout='active\n')),patch.object(server,'lms_request',return_value=inventory) as rpc:
                result=context.status()
            rpc.assert_called_once_with(['serverstatus','0','100'])
            self.assertNotIn('track',result)
            self.assertNotIn('playback',result)

    def test_absent_source_resolution_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'player.json').write_text(json.dumps({'id':'aa:bb:cc:dd:ee:ff'}))
            context=server.Context(root)
            inventory={'players_loop':[{'playerid':'aa:bb:cc:dd:ee:ff'}]}
            state={'mode':'play','playlist_loop':[{'title':'Sin resolución declarada','type':'flc'}]}
            with patch.object(server,'audio_devices',return_value=[]),patch.object(server,'read_hw_params',return_value=[]),patch.object(server,'command',return_value=SimpleNamespace(stdout='active\n')),patch.object(server,'lms_request',side_effect=[inventory,state]):
                result=context.status()
            self.assertNotIn('samplerate',result['track'])
            self.assertNotIn('sample_size',result['track'])

    def test_hardware_parameters_only_for_active_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'card2'/'pcm0p'/'sub0';path.mkdir(parents=True)
            (path/'hw_params').write_text('closed\n')
            self.assertEqual(server.read_hw_params(Path(directory)),[])
            (path/'hw_params').write_text('access: MMAP_INTERLEAVED\nformat: S32_LE\nchannels: 2\nrate: 96000 (96000/1)\n')
            result=server.read_hw_params(Path(directory))
            self.assertEqual(result[0]['rate'],'96000 (96000/1)')
            self.assertEqual(result[0]['card'],'card2')

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();root=Path(cls.tmp.name)
        salt=secrets.token_bytes(16)
        (root/'admin.json').write_text(json.dumps({'salt':salt.hex(),'hash':hashlib.pbkdf2_hmac('sha256',b'test-password',salt,200000).hex(),'iterations':200000}))
        cls.context=server.Context(root)
        cls.http=server.Server(('127.0.0.1',0),server.Handler);cls.http.context=cls.context
        cls.port=cls.http.server_address[1];cls.origin=f'http://127.0.0.1:{cls.port}'
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(2);cls.tmp.cleanup()

    def request(self,path,body=None,headers=None,method='POST'):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        actual={'Content-Type':'application/json','Origin':self.origin}
        actual.update(headers or {})
        conn.request(method,path,body=json.dumps(body).encode() if body is not None else b'{}',headers=actual)
        response=conn.getresponse();raw=response.read();result=(response.status,dict(response.getheaders()),json.loads(raw))
        conn.close();return result

    def login(self):
        code,headers,data=self.request('/api/session',{'password':'test-password'})
        self.assertEqual(code,200)
        return {'Cookie':headers['Set-Cookie'].split(';',1)[0],'X-Sonora-CSRF':data['csrf']}

    def test_login_cookie_http_only_and_same_site(self):
        code,headers,data=self.request('/api/session',{'password':'test-password'})
        self.assertEqual(code,200)
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertTrue(data['authenticated'])
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])

    def test_cross_origin_login_rejected(self):
        code,_,_=self.request('/api/session',{'password':'test-password'},{'Origin':'http://attacker.example'})
        self.assertEqual(code,403)

    def test_mutation_requires_session_and_csrf(self):
        self.assertEqual(self.request('/api/rescan',{})[0],401)
        headers=self.login();headers.pop('X-Sonora-CSRF')
        self.assertEqual(self.request('/api/rescan',{},headers)[0],403)

    def test_profile_enum_cannot_inject_command(self):
        headers=self.login()
        with patch.object(server,'command') as command:
            self.assertEqual(self.request('/api/profile',{'mode':'pure;reboot'},headers)[0],400)
            command.assert_not_called()

    def test_profile_calls_exact_argv(self):
        headers=self.login()
        with patch.object(server,'command') as command:
            command.return_value.returncode=0
            self.assertEqual(self.request('/api/profile',{'mode':'pure'},headers)[0],200)
            command.assert_called_once_with(['/usr/local/sbin/sonoractl','profile','--mode','pure'],timeout=30)

    def test_audio_requires_detected_device(self):
        headers=self.login()
        with patch.object(server,'audio_devices',return_value=[{'id':'hw:CARD=USB,DEV=0'}]), patch.object(server,'command') as command:
            self.assertEqual(self.request('/api/audio',{'device':'hw:CARD=Missing,DEV=0'},headers)[0],400)
            command.assert_not_called()
            self.assertEqual(self.request('/api/audio',{'device':'hw:CARD=USB,DEV=0;id'},headers)[0],400)
            command.assert_not_called()

    def test_nas_secret_is_stdin_not_argv_and_stderr_hidden(self):
        headers=self.login()
        with patch.object(server,'command') as command:
            command.return_value.returncode=1;command.return_value.stderr='secret-password'
            code,_,data=self.request('/api/nas',{'name':'M','host':'nas.local','share':'Music','username':'user','password':'secret-password'},headers)
            self.assertEqual(code,422)
            args,kwargs=command.call_args
            self.assertNotIn('secret-password',str(args));self.assertEqual(json.loads(kwargs['input_text']),{'password':'secret-password'})
            self.assertNotIn('secret-password',str(data))

    def test_rescan_rpc_is_fixed(self):
        headers=self.login()
        with patch.object(server,'lms_request',return_value={}) as rpc:
            self.assertEqual(self.request('/api/rescan',{},headers)[0],200)
            rpc.assert_called_once_with(['rescan'])

    def test_logout_revokes_session(self):
        headers=self.login();self.assertEqual(self.request('/api/logout',{},headers)[0],200)
        self.assertEqual(self.request('/api/rescan',{},headers)[0],401)

    def test_body_limit(self):
        headers=self.login()
        self.assertEqual(self.request('/api/profile',{'mode':'x'*server.MAX_BODY},headers)[0],413)

    def test_login_rate_limit(self):
        context=server.Context(Path(self.tmp.name))
        for _ in range(5):
            with self.assertRaises(server.APIError) as error: context.authenticate('wrong','test-ip')
            self.assertEqual(error.exception.status,401)
        with self.assertRaises(server.APIError) as error:context.authenticate('wrong','test-ip')
        self.assertEqual(error.exception.status,429)

if __name__=='__main__':unittest.main()
