import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from courseinbox.core import Inbox
from courseinbox.http import create_server

TOKEN='test-token-which-is-long-and-not-a-real-secret'
AT='2026-10-03T16:00:00+08:00'

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.inbox=Inbox(Path(cls.tmp.name)/'db.sqlite3')
        cls.server=create_server('127.0.0.1',0,cls.inbox,TOKEN,root=Path(__file__).resolve().parents[1])
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()
    def request(self,path,method='GET',body=None,auth=True,headers=None):
        h={'Content-Type':'application/json'}
        if auth: h['Authorization']='Bearer '+TOKEN
        h.update(headers or {})
        raw=None if body is None else json.dumps(body).encode()
        r=urllib.request.Request(self.url+path,raw,h,method=method)
        try:
            with urllib.request.urlopen(r,timeout=5) as response:
                return response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:
            return error.code,error.read(),error.headers
    def test_no_token_cannot_read_or_write_student_data(self):
        for path,method,body in [('/api/tasks','GET',None),('/api/messages','POST',{'text':'课程作业'})]:
            self.assertEqual(self.request(path,method,body,auth=False)[0],401)
    def test_loopback_bootstrap_and_host_origin_checks(self):
        status,body,h=self.request('/api/bootstrap',auth=False)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['token'],TOKEN)
        self.assertEqual(h['Cache-Control'],'no-store')
        self.assertEqual(self.request('/api/bootstrap',auth=False,headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/tasks',headers={'Origin':'https://evil.example'})[0],403)
    def test_invalid_json_and_payloads_are_client_errors(self):
        for body in [[],{'text':''},{'text':'实验报告','captured_at':'昨天'},{'text':'a'*30001}]:
            self.assertEqual(self.request('/api/messages','POST',body)[0],400)
    def test_text_proposal_confirm_and_calendar_are_real(self):
        status,body,_=self.request('/api/messages','POST',{'text':'《高等数学》 第一次作业截止10月13日20:00。','captured_at':AT,'scope':'API班'})
        self.assertEqual(status,201)
        p=json.loads(body)['proposals'][0]
        status,body,_=self.request('/api/proposals/'+p['id']+'/confirm','POST',{})
        self.assertEqual(status,200)
        task=json.loads(body)
        status,body,_=self.request('/api/tasks/'+task['id'],'PATCH',{'status':'submitted','expected_version':task['version']})
        self.assertEqual(json.loads(body)['status'],'submitted')
        status,body,h=self.request('/api/calendar.ics')
        self.assertEqual(status,200)
        self.assertIn('BEGIN:VEVENT',body.decode())
        self.assertIn('text/calendar',h['Content-Type'])
    def test_android_whitelist_and_replayed_event(self):
        payload={'package_name':'com.chaoxing.mobile','notification_key':'test:key:1','title':'《软件工程》 第三次作业','text':'截止10月12日23:59。','captured_at':AT,'scope':'手机班'}
        status,body,_=self.request('/api/mobile/notifications','POST',payload)
        self.assertEqual(status,201)
        self.assertEqual(json.loads(body)['message']['source'],'Android · com.chaoxing.mobile')
        status,body,_=self.request('/api/mobile/notifications','POST',payload)
        self.assertEqual(status,200)
        self.assertTrue(json.loads(body)['duplicate'])
        payload['package_name']='com.private.chat'
        self.assertEqual(self.request('/api/mobile/notifications','POST',payload)[0],403)
    def test_missing_resource_is_404_not_server_error(self):
        self.assertEqual(self.request('/api/tasks/nonexistent')[0],404)
    def test_encoded_traversal_cannot_read_local_db(self):
        self.assertEqual(self.request('/..%2fdata%2finbox.sqlite3')[0],404)

if __name__=='__main__': unittest.main()
