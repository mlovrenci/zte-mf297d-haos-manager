import io, json, sys, unittest, gzip
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]/"zte_manager"/"src"
sys.path.insert(0,str(ROOT))
from zte_api import RouterClient, RouterError

class FakeResponse:
    def __init__(self, body, headers=None, status=200):
        self.data=io.BytesIO(body);self.headers=headers or {};self.status=status
    def geturl(self):return "http://192.168.1.1/goform/goform_get_cmd_process"
    def read(self,n):return self.data.read(n)
    def __enter__(self):return self
    def __exit__(self,*a):pass

class FakeOpener:
    def __init__(self,body,headers=None):self.body=body;self.headers=headers or {};self.requests=[]
    def open(self,request,timeout=0):
        self.requests.append(request);return FakeResponse(self.body,self.headers)

class ResponseTests(unittest.TestCase):
    def client(self,body,headers=None):
        c=RouterClient("192.168.1.1");op=FakeOpener(body,headers);c.opener=op;return c,op
    def check(self,body,headers=None):
        c,op=self.client(body,headers);r=c._diagnose_reservation_body("/goform/goform_get_cmd_process?cmd=current_static_addr_list")
        self.assertNotIn("mac_addr",json.dumps(r)); self.assertNotIn("192.168.1.80",json.dumps(r))
        self.assertEqual(len(op.requests),1);self.assertTrue(op.requests[0].full_url.startswith("http://192.168.1.1/goform/goform_get_cmd_process"))
        return r
    def test_utf8_json(self):
        r=self.check(b'{"current_static_addr_list":[]}')
        self.assertEqual(r["status"],"field_present_empty");self.assertEqual(r["parsed_charset"],"utf-8-sig")
    def test_nonutf8_latin1_json(self):
        r=self.check(b'{"current_static_addr_list":[{"hostname":"Caf\xe9","mac_addr":"SECRET","ip":"192.168.1.80"}]}')
        self.assertEqual(r["status"],"field_present_nonempty");self.assertEqual(r["list_length"],1)
    def test_gzip_raw_magic(self):
        r=self.check(gzip.compress(b'{"current_static_addr_list":[]}'))
        self.assertEqual(r["status"],"field_present_empty");self.assertEqual(r["decoded_compression"],"gzip")
    def test_gzip_header(self):
        r=self.check(gzip.compress(b'{"current_static_addr_list":[]}'),{"Content-Encoding":"gzip"})
        self.assertEqual(r["status"],"field_present_empty")
    def test_html_returns_non_json(self):
        r=self.check(b'<html><body>login</body></html>',{"Content-Type":"text/html; charset=UTF-8"})
        self.assertEqual(r["status"],"non_json_payload");self.assertEqual(r["payload_kind"],"html_like")
    def test_invalid_binary(self):
        r=self.check(b'\xff\xfe\x00\x90')
        self.assertEqual(r["status"],"non_json_payload");self.assertEqual(r["payload_kind"],"unknown")
    def test_invalid_gzip(self):
        r=self.check(b'\x1f\x8b garbage')
        self.assertEqual(r["status"],"compression_error")
    def test_redact_secret_fields(self):
        r=self.check(b'{"current_static_addr_list":[{"ip":"192.168.1.80","mac_addr":"SECRET"}]}')
        self.assertEqual(r["list_length"],1);self.assertNotIn('SECRET',str(r))
    def test_only_after_decode_failure(self):
        c,op=self.client(b'{"current_static_addr_list": []}')
        def raise_decode(*a,**k):
            try:b'\xff'.decode('utf-8')
            except UnicodeDecodeError as e:raise RouterError('read failed') from e
        with patch.object(c,'_request',side_effect=raise_decode):
            v=c.probe_reservation_transport()
        self.assertEqual(v['get']['status'],'field_present_empty')
        self.assertEqual(v['post_read']['status'],'field_present_empty')
        self.assertEqual(len(op.requests),2)
        self.assertIsNone(op.requests[0].data);self.assertIsNotNone(op.requests[1].data)
        self.assertTrue(all('goform_get_cmd_process' in r.full_url for r in op.requests))

if __name__=='__main__':unittest.main()