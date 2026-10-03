"""Authenticated local HTTP API; no dependency beyond Python stdlib."""
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import socket
from datetime import datetime,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote
from .core import Inbox,ValidationError,Conflict,NotFound,now_iso,CN,parse_timestamp
from .agent import Agent,AgentError,provider_from_env
from .files import extract_file,MAX_UPLOAD

MAX_BODY=12*1024*1024
DEFAULT_PACKAGES=['com.chaoxing.mobile']
PACKAGE_RE=re.compile(r'[A-Za-z][\w]*(?:\.[A-Za-z][\w]*)+')

def load_settings(directory):
    path=Path(directory)/'settings.json'
    if path.exists():
        try:
            obj=json.loads(path.read_text(encoding='utf-8-sig'))
            packages=obj['allowed_packages']
            if isinstance(packages,list) and all(isinstance(p,str) and PACKAGE_RE.fullmatch(p) for p in packages):
                return {'allowed_packages':packages[:30]}
        except (ValueError,KeyError,TypeError,OSError): pass
    return {'allowed_packages':DEFAULT_PACKAGES.copy()}

def create_server(host,port,inbox,token,root=None,agent=None):
    root=Path(root or Path(__file__).resolve().parents[1])
    configured=agent or Agent(inbox,provider_from_env())
    settings=load_settings(inbox.path.parent)
    address_list={'localhost','127.0.0.1','::1'}
    if host not in ('0.0.0.0','::'):
        address_list.add(host)
    try:
        address_list.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError: pass
    class Handler(BaseHTTPRequestHandler):
        server_version='CourseInbox/0.1'
        protocol_version='HTTP/1.0'
        def log_message(self,fmt,*args):
            # Requests may contain credential-like strings; no URL/body logging.
            pass
        def response(self,status,payload,kind='application/json; charset=utf-8',filename=None):
            if isinstance(payload,(dict,list)):
                payload=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            elif isinstance(payload,str):
                payload=payload.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(payload)
        def guard(self):
            raw_host=self.headers.get('Host','')
            try:
                target=urlsplit('http://'+raw_host)
                host_name=target.hostname
                port_number=target.port or 80
            except ValueError:
                return self.response(403,{'error':'Host 无效。'}) or False
            if host_name not in address_list or port_number!=self.server.server_port or target.path:
                return self.response(403,{'error':'此 Host 未授权。'}) or False
            origin=self.headers.get('Origin')
            if origin:
                if origin!='http://'+raw_host:
                    return self.response(403,{'error':'请求来源未授权。'}) or False
            return True
        def auth(self):
            header=self.headers.get('Authorization','')
            if not hmac.compare_digest(header,'Bearer '+token):
                self.response(401,{'error':'需要访问令牌。本机打开可自动连接，手机请填写令牌。'})
                return False
            return True
        def body(self):
            value=self.headers.get('Content-Length')
            try: size=int(value or '0')
            except ValueError: raise ValidationError('Content-Length 无效。') from None
            if size<0 or size>MAX_BODY: raise ValidationError('请求超过 12 MB 上限。')
            if self.headers.get('Transfer-Encoding'): raise ValidationError('不支持分块上传。')
            if 'application/json' not in self.headers.get('Content-Type',''): raise ValidationError('请使用 JSON 请求。')
            try: result=json.loads(self.rfile.read(size))
            except (ValueError,UnicodeDecodeError): raise ValidationError('JSON 无效。') from None
            if not isinstance(result,dict): raise ValidationError('请求体必须为 JSON 对象。')
            return result
        def do_GET(self): self.handle_route('GET')
        def do_POST(self): self.handle_route('POST')
        def do_PATCH(self): self.handle_route('PATCH')
        def handle_route(self,method):
            try:
                self.connection.settimeout(15)
                if not self.guard(): return
                path=urlsplit(self.path).path
                if method=='GET' and path=='/api/health':
                    return self.response(200,{'status':'ok','app':'CourseInbox','version':'0.1.0'})
                if method=='GET' and path=='/api/bootstrap':
                    host_name=urlsplit('http://'+self.headers['Host']).hostname
                    if not ipaddress.ip_address(self.client_address[0]).is_loopback or host_name not in ('localhost','127.0.0.1','::1'):
                        return self.response(403,{'error':'远程访问请手动输入本机令牌。'})
                    return self.response(200,{'token':token})
                if not path.startswith('/api/'):
                    if method!='GET': return self.response(405,{'error':'方法不支持。'})
                    static={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
                    target=static.get(path)
                    if not target or not (root/'web'/target).is_file():
                        return self.response(404,{'error':'页面不存在。'})
                    kind=mimetypes.guess_type(target)[0] or 'application/octet-stream'
                    if kind.startswith('text/') or kind=='application/javascript': kind+='; charset=utf-8'
                    return self.response(200,(root/'web'/target).read_bytes(),kind)
                if not self.auth(): return
                if method=='GET':
                    if path=='/api/state':
                        return self.response(200,dict(tasks=inbox.tasks(),proposals=inbox.proposals(),messages=inbox.messages(),summary=inbox.dashboard(),agent=configured.info()))
                    if path=='/api/tasks': return self.response(200,inbox.tasks())
                    if path=='/api/messages': return self.response(200,inbox.messages())
                    if path=='/api/proposals': return self.response(200,inbox.proposals())
                    if path=='/api/dashboard': return self.response(200,inbox.dashboard())
                    if path=='/api/settings':
                        return self.response(200,dict(settings,agent=configured.info(),server_port=self.server.server_port,listen_host=host,addresses=sorted(address_list),ocr=os.name=='nt',pdf_optional=True))
                    if path=='/api/calendar.ics': return self.response(200,inbox.calendar(),'text/calendar; charset=utf-8','courseinbox.ics')
                    if path=='/api/export.json':
                        content=dict(version='0.1.0',exported_at=now_iso(),messages=inbox.messages(),proposals=inbox.proposals(None),tasks=[inbox.task_detail(t['id']) for t in inbox.tasks()])
                        return self.response(200,content,filename='courseinbox-backup.json')
                    if path.startswith('/api/tasks/'):
                        return self.response(200,inbox.task_detail(path.rsplit('/',1)[-1]))
                if method in ('POST','PATCH'):
                    body=self.body()
                    if method=='POST' and path=='/api/messages':
                        if set(body)-{'text','source','captured_at','course','scope','mode'}: raise ValidationError('消息字段不支持。')
                        text=body.get('text','')
                        at=body.get('captured_at') or now_iso()
                        selected=body.get('mode','default')
                        if selected not in ('rules','agent','default'): raise ValidationError('提取模式无效。')
                        selected_agent=Agent(inbox) if selected=='rules' else configured
                        if selected=='agent' and not configured.provider: raise ValidationError('服务端尚未配置模型，请选择规则模式。')
                        course,scope=body.get('course',''),body.get('scope','')
                        # Validate context before forwarding any source to a model.
                        from .core import clean_string
                        course=clean_string(course,'课程',100)
                        scope=clean_string(scope,'班级',100)
                        analysis=selected_agent.analyze(text,at,course,scope)
                        result=inbox.ingest(text,source=body.get('source','手动导入'),captured_at=at,course=course,scope=scope,
                                            candidates=analysis['candidates'],mode=analysis['mode'],trace=analysis['trace'])
                        result['answer'],result['limited']=analysis['answer'],analysis['limited']
                        return self.response(200 if result['duplicate'] else 201,result)
                    if method=='POST' and re.fullmatch(r'/api/messages/[a-f0-9]+/reanalyze',path):
                        if set(body)-{'mode'} or body.get('mode','rules')!='rules':
                            raise ValidationError('重新提取入口使用本地规则，请传空对象或 mode=rules。')
                        return self.response(200,inbox.reanalyze(path.split('/')[3]))
                    if method=='POST' and path=='/api/files/extract':
                        if set(body)-{'filename','content_base64'}: raise ValidationError('文件字段不支持。')
                        name=body.get('filename','')
                        if not isinstance(name,str) or len(name)>240: raise ValidationError('文件名无效。')
                        raw=body.get('content_base64','')
                        if not isinstance(raw,str) or len(raw)>MAX_BODY: raise ValidationError('文件内容无效。')
                        try: data=base64.b64decode(raw,validate=True)
                        except (ValueError,binascii.Error): raise ValidationError('文件编码无效。') from None
                        text,engine=extract_file(name,data,root)
                        if len(text)>30000: raise ValidationError('识别内容超过 30000 字，请分段导入。')
                        return self.response(200,{'text':text,'engine':engine,'needs_review':True})
                    if method=='POST' and re.fullmatch(r'/api/proposals/[a-f0-9]+/confirm',path):
                        ident=path.split('/')[3]
                        return self.response(200,inbox.confirm(ident,body))
                    if method=='POST' and re.fullmatch(r'/api/proposals/[a-f0-9]+/dismiss',path):
                        return self.response(200,inbox.dismiss(path.split('/')[3]))
                    if method=='PATCH' and re.fullmatch(r'/api/tasks/[a-f0-9]+',path):
                        return self.response(200,inbox.patch_task(path.rsplit('/',1)[-1],body))
                    if method=='POST' and path=='/api/assistant':
                        return self.response(200,configured.ask(body.get('question',''),body.get('course',''),body.get('scope')))
                    if method=='POST' and path=='/api/settings':
                        if set(body)!={'allowed_packages'}: raise ValidationError('只支持设置应用包名白名单。')
                        packages=body['allowed_packages']
                        if not isinstance(packages,list) or len(packages)>30 or any(not isinstance(p,str) or not PACKAGE_RE.fullmatch(p) or len(p)>150 for p in packages): raise ValidationError('白名单为最多30个完整应用包名。')
                        settings['allowed_packages']=list(dict.fromkeys(packages))
                        directory=inbox.path.parent
                        directory.mkdir(exist_ok=True)
                        with inbox.lock:
                            target=directory/'settings.json'
                            temp=directory/'settings.json.tmp'
                            temp.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
                            os.replace(temp,target)
                        return self.response(200,settings)
                    if method=='POST' and path=='/api/mobile/notifications':
                        from .core import clean_string
                        parse_timestamp(body.get('captured_at'))
                        package=clean_string(body.get('package_name',''),'应用包名',150,True)
                        if package not in settings['allowed_packages']:
                            return self.response(403,{'error':'应用不在接收白名单中。'})
                        title=clean_string(body.get('title',''),'通知标题',500)
                        text=clean_string(body.get('text',''),'通知正文',28000)
                        key=clean_string(body.get('notification_key',''),'通知标识',1000,True)
                        # The timestamp is required: relative dates belong to posted time, not upload time.
                        result=inbox.ingest('\n'.join(x for x in [title,text] if x),source='Android · '+package,captured_at=body.get('captured_at'),
                                            course=body.get('course',''),scope=body.get('scope',''),event_key=key)
                        return self.response(200 if result['duplicate'] else 201,result)
                    if method=='POST' and path=='/api/demo':
                        return self.response(200,seed_demo(inbox))
                return self.response(404,{'error':'接口不存在。'})
            except NotFound as e: self.response(404,{'error':str(e)})
            except Conflict as e: self.response(409,{'error':str(e)})
            except ValidationError as e: self.response(400,{'error':str(e)})
            except AgentError as e: self.response(502,{'error':str(e),'suggestion':'可显式改用规则提取后重试。'})
            except (BrokenPipeError,ConnectionResetError,socket.timeout): pass
            except Exception:
                self.response(500,{'error':'本地服务发生异常，请查看启动窗口并保留当前输入。'})
    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=True
    return server

def seed_demo(inbox):
    current=datetime.now(CN).replace(microsecond=0)
    stamp=current.replace(hour=9,minute=0,second=0).isoformat()
    soon=(current+timedelta(hours=8)).replace(minute=0,second=0)
    later=current+timedelta(days=3)
    day=current+timedelta(days=5)
    notices=[
        f'《软件工程》 第三次作业：请提交实验报告、源代码。截止：{soon:%Y年%m月%d日 %H:%M}。',
        f'《高等数学》 第一次作业：请提交习题扫描件。截止：{later:%Y年%m月%d日} 20:00。',
        f'《数据库原理》 实验2：请提交 SQL 脚本、实验报告。截止：{day:%Y年%m月%d日} 18:00。'
    ]
    ids=[]
    for text in notices:
        result=inbox.ingest(text,source='示例 · 学习通',captured_at=stamp,scope='示例班级',sample=True)
        for p in result['proposals']:
            if p['status']=='confirmed': ids.append(p['task_id']); continue
            if p['before'] and not p['before']['sample']: continue
            try: ids.append(inbox.confirm(p['id'])['id'])
            except Conflict: pass
    # Missing deadline and extension are left for a person to confirm.
    inbox.ingest(f'《高等数学》 第一次作业原截止{later:%m月%d日}20:00，现延期到{(later+timedelta(days=1)):%m月%d日}18:00。',source='示例 · 班级群',captured_at=current.isoformat(),scope='示例班级',sample=True)
    inbox.ingest('《学术英语》 第二次作业：请提交演讲稿、演示文稿。具体截止时间稍后通知。',source='示例 · 课程通知',captured_at=stamp,scope='示例班级',sample=True)
    return dict(sample=True,message='已加载示例：3个已确认任务、延期草稿和缺少截止的草稿。',task_ids=ids)
