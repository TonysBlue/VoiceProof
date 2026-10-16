import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from voiceproof.server import Application, make_server, MAX_BYTES
from voiceproof.workflow import UserError

class Process:
    def __init__(self,*args,**kwargs): self.code=None
    def poll(self): return self.code
    def terminate(self): self.code=-15
    def kill(self): self.code=-9
    def wait(self,timeout=None): return self.code

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/'model');self.addCleanup(self.app.clear)
        self.app.model_dir.mkdir()
        for name in ('model.bin','config.json','tokenizer.json','vocabulary.txt'): (self.app.model_dir/name).touch()
        self.server=make_server(app=self.app)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.url+path,data=body,headers={'X-VoiceProof-Token':self.app.token} if headers is None else headers)
        return urllib.request.urlopen(req)

    def start_job(self):
        with patch('voiceproof.server.importlib.util.find_spec',return_value=True),patch('voiceproof.server.subprocess.Popen',Process):
            self.app.begin(io.BytesIO(b'media'), 'test.mp4','你好',[])

    def test_security_static_and_mutations(self):
        with self.request('/') as response:
            self.assertIn(self.app.token,response.read().decode())
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        for path,body,headers in [('/status',None,{'X-VoiceProof-Token':'bad'}),('/clear',b'',{}),('/clear',b'',{'X-VoiceProof-Token':self.app.token,'Origin':'https://evil.test'}),('/',None,{'Host':'evil.test'})]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path,body,headers)
            self.assertEqual(error.exception.code,403)
        with self.request('/clear',b'') as response:
            self.assertEqual(json.load(response),{'ok':True})

    def test_localhost_preview_forwarding_and_origin_protection(self):
        headers = {'Host':'localhost:59666', 'Origin':'http://localhost:59666',
                   'X-VoiceProof-Token':self.app.token}
        with self.request('/', headers=headers) as response:
            self.assertEqual(response.status,200)
        with self.request('/clear', b'', headers) as response:
            self.assertEqual(response.status,200)
        for host, origin in [('localhost.evil.test:59666','http://localhost.evil.test:59666'),
                             ('localhost:59666','http://localhost:12345'),
                             ('localhost:99999','http://localhost:99999')]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/', headers={'Host':host,'Origin':origin})
            self.assertEqual(error.exception.code,403)

    def test_job_lifecycle_cancel_expire_timeout_and_media_range(self):
        self.start_job(); directory=self.app.directory
        self.assertEqual(self.app.status()['state'],'running')
        with self.assertRaises(UserError): self.app.begin(setup=True)
        (directory/'audio.wav').write_bytes(b'0123456789')
        (directory/'result.json').write_text(json.dumps({'issues':[]}))
        self.app.process.code=0
        self.assertEqual(self.app.status()['state'],'done')
        with self.request('/media',headers={'Cookie':'vp='+self.app.token,'Range':'bytes=2-5'}) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345')
        with self.assertRaises(urllib.error.HTTPError): self.request('/media')
        self.app.clear();self.assertFalse(directory.exists())
        self.start_job();directory=self.app.directory;self.app.started-=901
        self.assertEqual(self.app.status()['state'],'failed');self.assertFalse(directory.exists())
        self.start_job();directory=self.app.directory;self.app.touched-=1801
        self.assertEqual(self.app.status()['state'],'failed');self.assertFalse(directory.exists())

    def test_invalid_inputs_and_worker_failure(self):
        with patch('voiceproof.server.importlib.util.find_spec',return_value=True):
            for filename,script in [('file.exe','你好'),('file.mp4',''),('file.mp4','字'*20001)]:
                with self.assertRaises(UserError): self.app.begin(io.BytesIO(b'data'),filename,script,[])
        self.start_job();self.app.process.code=1
        self.assertEqual(self.app.status()['state'],'failed')
        self.assertNotIn('Traceback',self.app.status()['message'])

    def test_graphical_upload_uses_form_and_not_json(self):
        boundary='vp-test'
        parts=[]
        for name,value in [('script','你好'),('terms','测试')]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="test.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()+b'video\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        with patch('voiceproof.server.importlib.util.find_spec',return_value=True),patch('voiceproof.server.subprocess.Popen',Process):
            with self.request('/check',b''.join(parts),{'X-VoiceProof-Token':self.app.token,'Content-Type':'multipart/form-data; boundary='+boundary}) as response:
                self.assertEqual(response.status,200)
        self.assertEqual((self.app.directory/'source').read_bytes(),b'video')
        self.assertEqual(json.loads((self.app.directory/'request.json').read_text())['script'],'你好')

    def test_upload_limits_and_model_readiness(self):
        with patch('voiceproof.server.importlib.util.find_spec',return_value=True),patch('voiceproof.server.MAX_BYTES',4):
            with self.assertRaisesRegex(UserError,'超过100MB'):
                self.app.begin(io.BytesIO(b'12345'),'large.wav','你好',[])
            self.assertIsNone(self.app.directory)
        (self.app.model_dir/'tokenizer.json').unlink()
        with self.assertRaisesRegex(UserError,'安装本地语音引擎'):
            self.app.begin(io.BytesIO(b'123'),'test.wav','你好',[])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/check',b'',{'X-VoiceProof-Token':self.app.token,'Content-Length':str(MAX_BYTES+200001)})
        self.assertEqual(error.exception.code,400)
