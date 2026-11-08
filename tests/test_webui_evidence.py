import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager/src'))
from webui_evidence import inspect, inspect_wifi_modules, safe_url, MAX_FILE_BYTES, module_references, literal_config
BASE='http://192.168.1.1'
class Response(io.BytesIO):
 def __init__(self,url,body):super().__init__(body);self.url=url;self.headers={}
 def geturl(self):return self.url
class Opener:
 def __init__(self,mapping):self.mapping=mapping;self.requests=[]
 def open(self,req,timeout):
  self.requests.append(req)
  value=self.mapping[req.full_url]
  if isinstance(value,Exception):raise value
  return Response(req.full_url,value)
class EvidenceTests(unittest.TestCase):
 def test_same_origin_static_only(self):
  for path in ['http://example.com/x.js','/goform/x.js','/x%2ejs','/api/state','//example.com/x.js','javascript:alert(1)','/x\\y.js']:
   self.assertIsNone(safe_url(BASE,BASE+'/',path))
  self.assertEqual(safe_url(BASE,BASE+'/', '/js/a.js?v=1'),BASE+'/js/a.js')
 def test_references_not_raw_source_or_write_support(self):
  o=Opener({BASE+'/':b'<script src="/js/a.js"></script><script src="http://evil.test/a.js"></script>',BASE+'/js/a.js':b'var password="SECRET"; goformId="SET_WIFI_INFO"; wifiEnabled;'} )
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(len(r['files']),2);self.assertFalse(r['write_verified']);self.assertNotIn('SECRET',str(r))
  self.assertEqual(r['files'][1]['command_references'],['SET_WIFI_INFO'])
  self.assertTrue(all(q.get_method()=='GET' and '/goform' not in q.full_url for q in o.requests))
 def test_external_redirect_is_never_followed(self):
  o=Opener({BASE+'/':HTTPError(BASE+'/',302,'redirect',{'Location':'https://evil.test/a.js'},None)})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(len(o.requests),1);self.assertIn('redirect_blocked',r['issues'])
 def test_size_and_request_limits(self):
  o=Opener({BASE+'/':b'a'*(MAX_FILE_BYTES+1)})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['files'],[]);self.assertIn('size_limit',r['issues'])
 def test_same_origin_static_redirect_and_data_main(self):
  o=Opener({BASE+'/':HTTPError(BASE+'/',302,'redirect',{'Location':'/index.html'},None),BASE+'/index.html':b'<script data-main="js/main"></script>',BASE+'/js/main.js':b'var x=1;'})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual([x['path'] for x in r['files']],['/index.html','/js/main.js'])

 def test_literal_modules_only(self):
  self.assertEqual(module_references('require(["service", "text!secret", "../x", "exports"], fn);'),['service'])
  o=Opener({BASE+'/':b'<script data-main="js/main"></script>', BASE+'/js/main.js':b'require(["service"],fn)',BASE+'/js/service.js':b'SET_WIFI_SSID1_SETTINGS'})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['files'][-1]['path'],'/js/service.js')
  self.assertEqual(r['files'][-1]['command_references'],['SET_WIFI_SSID1_SETTINGS'])

 def test_literal_path_aliases(self):
  source=b'require.config({"baseUrl":"assets",paths:{service:"net/service"}});require(["service"],fn);'
  o=Opener({BASE+'/':b'<script data-main="main"></script>',BASE+'/main.js':source,BASE+'/assets/net/service.js':b'SET_WIFI_INFO'})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['files'][-1]['path'],'/assets/net/service.js')
  self.assertEqual(literal_config('paths:{service: compute()}')['paths'],{})

 def test_loader_defaults_do_not_override_data_main_base(self):
  o=Opener({BASE+'/':b'<script src="/js/require.js" data-main="js/main"></script>',BASE+'/js/require.js':b'var defaults={baseUrl:"./"};',BASE+'/js/main.js':b'require(["service"],fn)',BASE+'/js/service.js':b'SET_WIFI_INFO'})
  r=inspect(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['files'][-1]['path'],'/js/service.js')

 def test_pinned_source_rejects_changed_asset_and_firmware(self):
  from webui_evidence import wifi_source
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'other'}},{}))
  o=Opener({})
  self.assertEqual(wifi_source(c,o)['status'],'firmware_mismatch');self.assertFalse(o.requests)
  c.query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{})
  o=Opener({BASE+'/js/service.js':b'SECRET unexpected source SET_WIFI_INFO'})
  result=wifi_source(c,o)
  self.assertEqual(result['status'],'asset_mismatch');self.assertEqual(result['excerpts'],[])

 def test_wifi_module_scan_only_reads_fixed_static_paths_and_literal_wifi_modules(self):
  o=Opener({
   BASE+'/js/config/menu.js':b'const menu={wifi:"wifi/basic",wireless:"wifi/advance",unsafe:"../goform/SET_WIFI_INFO"};',
   BASE+'/js/router.js':b'define(["service", "wifi/security", "other"],fn);',
   BASE+'/js/config/config.js':b'paths: {wifi: "wifi"};',
   BASE+'/js/wifi/basic.js':b'var channel="Channel";',
   BASE+'/js/wifi/advance.js':b'var width="wifi_11n_cap";',
   BASE+'/js/wifi/security.js':b'var secret="DO_NOT_ECHO";'
  })
  r=inspect_wifi_modules(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['scan_scope'],'wifi_modules')
  self.assertEqual([f['path'] for f in r['files']],
                   ['/js/config/menu.js','/js/router.js','/js/config/config.js',
                    '/js/wifi/basic.js','/js/wifi/advance.js','/js/wifi/security.js'])
  self.assertEqual(r['files'][0]['wifi_literal_modules'],['wifi/basic','wifi/advance'])
  self.assertNotIn('DO_NOT_ECHO',str(r))
  self.assertFalse(r['write_verified'])
  self.assertTrue(all(req.get_method()=='GET' and '/goform' not in req.full_url
                      for req in o.requests))

 def test_wifi_module_scan_cannot_leave_router_on_redirect(self):
  o=Opener({BASE+'/js/config/menu.js':HTTPError(BASE+'/js/config/menu.js',302,'redirect',
                  {'Location':'https://evil.test/menu.js'},None),
            BASE+'/js/router.js':b'', BASE+'/js/config/config.js':b''})
  r=inspect_wifi_modules(SimpleNamespace(base=BASE),opener=o)
  self.assertIn('redirect_blocked',r['issues'])
  self.assertEqual(len(o.requests),3)
