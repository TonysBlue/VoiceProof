"""Loopback-only browser product. One bounded job, no durable user storage."""
from __future__ import annotations
import atexit
import cgi
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .text import tokens
from .workflow import UserError

MAX_BYTES = 100 * 1024 * 1024
EXTENSIONS = {'.wav','.mp3','.m4a','.mp4','.mov','.webm','.flac','.ogg'}
STATIC = Path(__file__).parent/'static'


class Application:
    def __init__(self, model_dir=None):
        self.model_dir = Path(model_dir or os.environ.get('VOICEPROOF_MODEL_DIR', Path.home()/'.cache/voiceproof/small'))
        self.directory = None
        self.process = None
        self.lock = threading.RLock()
        self.started = self.touched = 0
        self.setup = False
        self.failure = None
        self.token = secrets.token_urlsafe(32)

    def clear(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
            if self.directory:
                shutil.rmtree(self.directory, ignore_errors=True)
            self.directory = None
            self.failure = None

    def ready(self):
        return bool(importlib.util.find_spec('faster_whisper')) and all((self.model_dir/name).is_file() for name in ('model.bin','config.json','tokenizer.json','vocabulary.txt'))

    def begin(self, media=None, filename='', script='', terms=None, setup=False):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise UserError('正在处理一个任务，请等待完成或先清空取消。')
            if not importlib.util.find_spec('faster_whisper'):
                raise UserError('运行环境缺少语音引擎依赖，请联系内部安装维护人员完成安装。')
            if not setup:
                if not self.ready():
                    raise UserError('请先点击安装本地语音引擎，完成后再检查。')
                if Path(filename).suffix.lower() not in EXTENSIONS:
                    raise UserError('格式不支持，请选择 WAV、MP3、M4A、MP4、MOV、WebM、FLAC 或 OGG。')
                if not tokens(script) or len(script) > 20000:
                    raise UserError('请提供包含文字的原稿，最多20000字。')
                if not isinstance(terms, list) or len(terms) > 100 or any(not isinstance(t,str) or len(t)>100 for t in terms):
                    raise UserError('术语最多100项，每项最多100字。')
            self.clear()
            self.directory = Path(tempfile.mkdtemp(prefix='voiceproof-'))
            self.started = self.touched = time.monotonic()
            self.setup = setup
            try:
                if not setup:
                    with (self.directory/'source').open('wb') as out:
                        total = 0
                        while chunk := media.read(1024*1024):
                            total += len(chunk)
                            if total > MAX_BYTES:
                                raise UserError('素材超过100MB，请压缩或分段导出。')
                            out.write(chunk)
                    if not total:
                        raise UserError('请选择非空音视频文件。')
                    (self.directory/'request.json').write_text(json.dumps(dict(script=script, terms=terms)), encoding='utf-8')
                command = [sys.executable, '-m', 'voiceproof.worker', str(self.directory), str(self.model_dir)]
                if setup:
                    command.append('setup')
                environment = dict(os.environ, HF_HUB_DISABLE_TELEMETRY='1')
                if not setup:
                    environment['HF_HUB_OFFLINE'] = '1'
                self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
            except Exception:
                self.clear()
                raise

    def status(self):
        with self.lock:
            now = time.monotonic()
            if self.directory and now-self.touched > 1800:
                self.clear()
                self.failure = '闲置超过30分钟，本次资料已自动删除，请重新选择素材。'
            if self.process and self.process.poll() is None and now-self.started > 900:
                self.clear()
                self.failure = '处理超过15分钟，已停止并删除资料。请分段检查或换用性能更好的电脑。'
            result = dict(ready=self.ready(), state='idle', message=self.failure or '请选择音视频与原稿')
            if self.failure:
                result['state'] = 'failed'
            if self.directory:
                self.touched = now
                path = self.directory/'result.json'
                if path.exists():
                    payload = json.loads(path.read_text(encoding='utf-8'))
                    if 'error' in payload:
                        result.update(state='failed', message=payload['error'])
                    elif self.setup:
                        result.update(state='installed', message='本地引擎已准备好，可以开始检查', ready=True)
                    else:
                        result.update(state='done', report=payload, message='检查完成，请逐项回听复核')
                elif self.process.poll() is not None:
                    result.update(state='failed', message='本地处理意外停止，请清空后重试，或联系内部维护人员。')
                else:
                    path = self.directory/'progress.json'
                    message = json.loads(path.read_text(encoding='utf-8'))['message'] if path.exists() else '正在准备本地处理'
                    result.update(state='running', message=message)
            return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log filenames, scripts, tokens or requests.

    def guard(self, mutation=False):
        # Local preview proxies may use localhost and a different forwarded port.
        import re
        host = self.headers.get('Host', '')
        local_host = re.fullmatch(r'(?:127\.0\.0\.1|localhost):([0-9]{1,5})', host)
        valid = local_host is not None and 0 < int(local_host[1]) <= 65535
        if not valid or self.headers.get('Origin', 'http://'+host) != 'http://'+host:
            self.send_error(403)
            return False
        if mutation and self.headers.get('X-VoiceProof-Token') != self.server.app.token:
            self.send_error(403)
            return False
        return True

    def respond(self, payload, status=200, kind='application/json; charset=utf-8'):
        body = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload,dict) else payload
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        self.send_header('Set-Cookie', f'vp={self.server.app.token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.guard():
            return
        path = urlsplit(self.path).path
        if path == '/':
            self.respond((STATIC/'index.html').read_bytes().replace(b'__TOKEN__', self.server.app.token.encode()), kind='text/html; charset=utf-8')
        elif path in ('/app.js','/style.css'):
            self.respond((STATIC/path[1:]).read_bytes(), kind='text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
        elif path == '/status':
            if self.headers.get('X-VoiceProof-Token') != self.server.app.token:
                self.send_error(403)
                return
            self.respond(self.server.app.status())
        elif path == '/media':
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie',''))
            except Exception:
                self.send_error(403)
                return
            if not cookie.get('vp') or cookie['vp'].value != self.server.app.token:
                self.send_error(403)
                return
            with self.server.app.lock:
                directory = self.server.app.directory
                file = directory/'audio.wav' if directory else None
                if not file or not file.is_file() or self.server.app.status()['state'] != 'done':
                    self.send_error(404)
                    return
                size = file.stat().st_size
            self.connection.settimeout(10)
            start, end = 0, size-1
            ranged = self.headers.get('Range')
            if ranged:
                import re
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', ranged)
                if not match:
                    self.send_error(416)
                    return
                start = int(match[1])
                end = min(size-1, int(match[2])) if match[2] else size-1
                if start > end:
                    self.send_error(416)
                    return
            self.send_response(206 if ranged else 200)
            self.send_header('Content-Type','audio/wav')
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Length',str(end-start+1))
            self.send_header('Cache-Control','no-store')
            if ranged:
                self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            position = start
            while position <= end:
                with self.server.app.lock:
                    if self.server.app.directory != directory or not file.exists():
                        return
                    with file.open('rb') as stream:
                        stream.seek(position)
                        chunk = stream.read(min(65536, end-position+1))
                if not chunk:
                    return
                try:
                    self.wfile.write(chunk)
                except OSError:
                    return
                position += len(chunk)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.guard(mutation=True):
            return
        try:
            size = int(self.headers.get('Content-Length','0'))
            if size < 0 or size > MAX_BYTES+200000 or self.headers.get('Transfer-Encoding'):
                raise UserError('上传超过100MB或请求格式不支持，请缩小文件后重试。')
            self.connection.settimeout(30)
            if self.path == '/clear':
                self.server.app.clear()
            elif self.path == '/setup':
                self.server.app.begin(setup=True)
            elif self.path == '/check':
                if not self.headers.get('Content-Type','').startswith('multipart/form-data;'):
                    raise UserError('请通过页面选择文件并填写原稿。')
                form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                        environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE':self.headers['Content-Type'], 'CONTENT_LENGTH':str(size)}, limit=size)
                if 'media' not in form or not getattr(form['media'],'filename',None):
                    raise UserError('请选择一个音视频文件。')
                self.server.app.begin(form['media'].file, form['media'].filename,
                                      form.getfirst('script',''), [t.strip() for t in form.getfirst('terms','').splitlines() if t.strip()])
            else:
                self.respond({'error':'找不到该操作，请刷新页面。'},404)
                return
            self.respond({'ok':True})
        except (UserError, ValueError, TypeError):
            error = sys.exc_info()[1]
            self.respond({'error':str(error) if isinstance(error,UserError) else '输入格式异常，请重新选择文件与原稿。'},400)
        except Exception:
            self.respond({'error':'本机服务暂时无法处理，请重试或检查磁盘空间。'},500)


def make_server(port=0, app=None):
    server = ThreadingHTTPServer(('127.0.0.1',port), Handler)
    server.daemon_threads = True
    server.app = app or Application()
    return server


def main():
    server = make_server()
    atexit.register(server.app.clear)
    def cleanup():
        while True:
            time.sleep(30)
            with server.app.lock:
                # A stale browser cannot keep data alive without requesting status.
                if server.app.directory and time.monotonic()-server.app.touched > 1800:
                    server.app.clear()
                elif server.app.process and server.app.process.poll() is None and time.monotonic()-server.app.started > 900:
                    server.app.clear()
                    server.app.failure = '处理超时，已停止并删除资料，请分段重试。'
    threading.Thread(target=cleanup, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    print('VoiceProof 本机界面：'+url)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.app.clear()

if __name__ == '__main__':
    main()
