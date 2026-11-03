import io, json, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"zte_manager"/"src"))
from zte_api import RouterClient

class Response:
    status=200
    headers={'Content-Type':'text/html'}
    def __init__(self,raw):self.f=io.BytesIO(raw)
    def read(self,n):return self.f.read(n)
    def geturl(self):return 'http://192.168.1.1/goform/goform_get_cmd_process'
    def __enter__(self):return self
    def __exit__(self,*args):return False
class Opener:
    def __init__(self,raw):self.raw=raw
    def open(self,*args,**kwargs):return Response(self.raw)
class MalformedB08Recovery(unittest.TestCase):
    def diagnose(self,raw):
        c=RouterClient('192.168.1.1');c.opener=Opener(raw)
        return c._diagnose_reservation_body('/goform/goform_get_cmd_process?cmd=current_static_addr_list')
    def test_nonutf8_byte_plus_raw_control_in_json_string(self):
        raw=b'{"current_static_addr_list":[{"hostname":"secret\xff\nHost", "ip":"192.168.1.80", "mac_addr":"11:22:33:44:55:66"}]}'
        result=self.diagnose(raw)
        self.assertEqual(result['status'],'field_present_nonempty')
        self.assertEqual(result['list_length'],1)
        self.assertFalse(result['utf8_valid'])
        self.assertEqual(result['recovery_method'],'tolerate_control_chars')
        self.assertTrue(result['recovered_untrusted_values'])
        output=json.dumps(result)
        self.assertNotIn('secret',output)
        self.assertNotIn('192.168.1.80',output)
        self.assertNotIn('11:22:33:44:55:66',output)
    def test_records_only_in_opt_in_local_view(self):
        raw=b'{"current_static_addr_list":[{"hostname":"Office\xff\nHost", "ip":"192.168.1.80", "mac_addr":"11:22:33:44:55:66"}]}'
        c=RouterClient('192.168.1.1');c.opener=Opener(raw)
        result=c._diagnose_reservation_body('/goform/goform_get_cmd_process?cmd=current_static_addr_list',include_records=True)
        self.assertEqual(result['list_length'],1)
        self.assertEqual(result['records'][0]['ip'],'192.168.1.80')
        self.assertEqual(len(result['records']),1)
        self.assertEqual(result['status'],'field_present_nonempty')
        self.assertNotIn('records',self.diagnose(raw))

    def test_empty_list_with_bad_byte_elsewhere(self):
        raw=b'{"current_static_addr_list":[],"random":"\xff\x00"}'
        r=self.diagnose(raw)
        self.assertEqual(r['status'],'field_present_empty')
        self.assertEqual(r['list_length'],0)
        self.assertEqual(r['recovery_method'],'tolerate_control_chars')
    def test_unquoted_corrupt_byte_fails_closed(self):
        raw=b'{"current_static_addr_list":\xff}'
        r=self.diagnose(raw)
        self.assertEqual(r['status'],'non_json_payload')
        self.assertIn('json_analysis',r)
    def test_nested_stringified_list_with_control(self):
        raw=b'{"current_static_addr_list":"[\\\"broken\nname\\\"]"}'
        r=self.diagnose(raw)
        self.assertTrue(r['status'].startswith('field_present'))
        self.assertNotIn('broken',json.dumps(r))
    def test_html_does_not_recover(self):
        r=self.diagnose(b'<html>current_static_addr_list</html>')
        self.assertEqual(r['status'],'non_json_payload')
        self.assertNotIn('recovery_method',r)
if __name__=='__main__':unittest.main()