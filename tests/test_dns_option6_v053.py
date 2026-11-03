import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'zte_manager'/'src'))
import dns_option6_probe as probe

class FakeClient:
    base='http://192.168.1.1'
    timeout=3
    def __init__(self, responses=None):
        self.responses=responses or {}
        self.opener=MagicMock()
    def get(self,fields):
        return self.responses.get(fields[0],{})

class Tests(unittest.TestCase):
    def test_empty_or_absent_not_support(self):
        self.assertEqual(probe.classify_key_response('dhcp_dns',{}),{'status':'absent'})
        self.assertEqual(probe.classify_key_response('dhcp_dns',{'dhcp_dns':''}),{'status':'empty'})
    def test_manual_wan_not_considered_dhcp(self):
        with patch.object(probe,'probe_webui_resources',return_value={}):
            r=probe.probe_dns_option6(FakeClient({'dns_mode':{'dns_mode':'manual'}}))
        self.assertEqual(r['status'],'unconfirmed')
        self.assertFalse(r['option6_verified'])
    def test_candidate_value_not_verified(self):
        with patch.object(probe,'probe_webui_resources',return_value={}):
            r=probe.probe_dns_option6(FakeClient({'dhcp_dns':{'dhcp_dns':'192.168.1.18'}}))
        self.assertEqual(r['status'],'candidate_found')
        self.assertFalse(r['option6_verified'])
    def test_webui_marker_without_raw_content(self):
        r=probe.scan_resource_response(b"some config dhcp_dns uses DHCP_SETTING",'application/javascript','')
        self.assertIn('dhcp_dns',r['markers'])
        self.assertNotIn('raw',r)
        self.assertNotIn('body',r)
    def test_webui_download_bounded(self):
        self.assertEqual(probe.scan_resource_response(b'0'*(probe.MAX_BYTES+1),'text/html','')['status'],'too_large')
    def test_same_host_redirect_only(self):
        c=FakeClient()
        response=MagicMock()
        response.geturl.return_value='https://example.com/js/adm/lan.js'
        response.__enter__.return_value=response
        c.opener.open.return_value=response
        with patch.object(probe,'WEBUI_PATHS',('/js/adm/lan.js',)):
            out=probe.probe_webui_resources(c)
        self.assertEqual(out['/js/adm/lan.js']['status'],'unexpected_redirect')
    def test_no_write_method_in_probe_module(self):
        src=Path(probe.__file__).read_text()
        self.assertNotIn('goform_set_cmd_process',src)

if __name__=='__main__':unittest.main()