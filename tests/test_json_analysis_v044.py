import io
import json
import unittest
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'zte_manager'/'src'
sys.path.insert(0,str(ROOT))
from zte_api import RouterClient

class FakeResponse:
    def __init__(self, raw):
        self.raw=io.BytesIO(raw)
        self.status=200
        self.headers={'Content-Type':'text/html'}
    def read(self,n):return self.raw.read(n)
    def geturl(self):return 'http://192.168.1.1/goform/goform_get_cmd_process'
    def __enter__(self):return self
    def __exit__(self,*args):return False
class Opener:
    def __init__(self,raw):self.raw=raw
    def open(self,*args,**kwargs):return FakeResponse(self.raw)

class DetailedResponseTests(unittest.TestCase):
    def probe(self,raw):
        client=RouterClient('192.168.1.1')
        client.opener=Opener(raw)
        value=client._diagnose_reservation_body('/goform/goform_get_cmd_process?cmd=current_static_addr_list')
        return value
    def test_invalid_control_character(self):
        raw=b'{"current_static_addr_list":[{"name":"Host\nname","mac":"AA:BB:CC:DD:EE:FF", "ip":"192.168.1.80"}]}'
        r=self.probe(raw)
        self.assertEqual(r['status'],'field_present_nonempty')
        self.assertEqual(r['payload_kind'],'json_like')
        self.assertTrue(r['field_token_present'])
        self.assertTrue(r['utf8_valid'])
        self.assertEqual(r['recovery_method'],'tolerate_control_chars')
        self.assertEqual(r['list_length'],1)
        self.assertNotIn('192.168.1.80',json.dumps(r))
        self.assertNotIn('AA:BB:CC:DD:EE:FF',json.dumps(r))
    def test_wrong_delimiter_with_invalid_utf8(self):
        raw=b'{"current_static_addr_list": [\xfffoo]}'
        r=self.probe(raw)
        self.assertEqual(r['status'],'non_json_payload')
        self.assertFalse(r['utf8_valid'])
        self.assertEqual(r['utf8_first_invalid_byte'],len(b'{"current_static_addr_list": ['))
        self.assertIn('json_analysis',r)
        self.assertLessEqual(len(r['json_analysis']),4)
        self.assertNotIn('foo',json.dumps(r))
    def test_unexpected_html(self):
        r=self.probe(b'<html>NOT JSON / some session cookie secret=123</html>')
        self.assertEqual(r['status'],'non_json_payload')
        self.assertFalse(r['field_token_present'])
        self.assertNotIn('secret',json.dumps(r))
    def test_normal_json_list(self):
        raw=b'{"current_static_addr_list": [{"ip":"192.168.1.80", "mac_addr":"SECRET"}]}'
        r=self.probe(raw)
        self.assertEqual(r['status'],'field_present_nonempty')
        self.assertEqual(r['list_length'],1)
        self.assertNotIn('SECRET',json.dumps(r))
    def test_http_mime_not_indicator(self):
        raw=b'{"current_static_addr_list":[]}'
        r=self.probe(raw)
        self.assertEqual(r['status'],'field_present_empty')
        self.assertEqual(r['content_type'],'text/html')

if __name__=='__main__': unittest.main()