import io
import hashlib
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager/src'))
from webui_evidence import (inspect, inspect_wifi_modules, inspect_wifi_channels,
                            wifi_ui_source, wifi_feature_source, wifi_getter_source,
                            WIFI_UI_PINNED,
                            WIFI_FEATURE_PINNED, safe_url, MAX_FILE_BYTES,
                            module_references, literal_config)
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
   BASE+'/js/config/cpe/MF297D/config.js':b'define({PRODUCT_TYPE:"CPE"});',
   BASE+'/js/config/cpe/MF297D/menu_4ggateway.js':b'[{hash:"#wifi",path:"wifi/device",level:"2"}]',
   BASE+'/js/wifi/basic.js':b'var channel="Channel";',
   BASE+'/js/wifi/advance.js':b'var width="wifi_11n_cap";',
   BASE+'/js/wifi/security.js':b'var secret="DO_NOT_ECHO";',
   BASE+'/js/wifi/device.js':b'var channel="m_Channel";'
  })
  r=inspect_wifi_modules(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(r['scan_scope'],'wifi_modules')
  self.assertEqual([f['path'] for f in r['files']],
                   ['/js/config/menu.js','/js/router.js','/js/config/config.js',
                    '/js/config/cpe/MF297D/config.js','/js/config/cpe/MF297D/menu_4ggateway.js',
                    '/js/wifi/basic.js','/js/wifi/advance.js','/js/wifi/security.js',
                    '/js/wifi/device.js'])
  self.assertEqual(r['files'][0]['wifi_literal_modules'],['wifi/basic','wifi/advance'])
  self.assertNotIn('DO_NOT_ECHO',str(r))
  self.assertFalse(r['write_verified'])
  self.assertTrue(all(req.get_method()=='GET' and '/goform' not in req.full_url
                      for req in o.requests))

 def test_wifi_module_scan_cannot_leave_router_on_redirect(self):
  o=Opener({BASE+'/js/config/menu.js':HTTPError(BASE+'/js/config/menu.js',302,'redirect',
                  {'Location':'https://evil.test/menu.js'},None),
            BASE+'/js/router.js':b'', BASE+'/js/config/config.js':b'',
            BASE+'/js/config/cpe/MF297D/config.js':b'',
            BASE+'/js/config/cpe/MF297D/menu_4ggateway.js':b''})
  r=inspect_wifi_modules(SimpleNamespace(base=BASE),opener=o)
  self.assertIn('redirect_blocked',r['issues'])
  self.assertEqual(len(o.requests),5)

 def test_pinned_wifi_ui_source_requires_exact_firmware_and_both_asset_hashes(self):
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'wrong'}},{}))
  o=Opener({})
  self.assertEqual(wifi_ui_source(c,o)['status'],'firmware_mismatch')
  self.assertFalse(o.requests)
  c.query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{})
  menu=b'define(["service"],fn);';router=b'define(["config/menu"],fn);'
  o=Opener({BASE+'/js/config/menu.js':menu,BASE+'/js/router.js':router})
  with patch.dict(WIFI_UI_PINNED,{'/js/config/menu.js':hashlib.sha256(menu).hexdigest(),
                                   '/js/router.js':hashlib.sha256(router).hexdigest()},clear=True):
   r=wifi_ui_source(c,o)
  self.assertEqual(r['status'],'pinned_static_source_only')
  self.assertEqual([x['source'] for x in r['files']],[menu.decode(),router.decode()])
  self.assertTrue(all(q.get_method()=='GET' and '/goform' not in q.full_url for q in o.requests))
  self.assertFalse(r['write_verified'])

 def test_pinned_wifi_ui_source_does_not_leak_partial_asset_on_changed_file(self):
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{}))
  o=Opener({BASE+'/js/config/menu.js':b'sensitive prototype text',BASE+'/js/router.js':b'unknown changed'})
  with patch.dict(WIFI_UI_PINNED,{'/js/config/menu.js':hashlib.sha256(b'sensitive prototype text').hexdigest(),
                                   '/js/router.js':WIFI_UI_PINNED['/js/router.js']},clear=True):
   r=wifi_ui_source(c,o)
  self.assertEqual(r['status'],'asset_mismatch')
  self.assertEqual(r['files'],[])

 def test_two_fixed_wifi_channel_modules_are_get_only(self):
  o=Opener({BASE+'/js/wifi/wifi_channel.js':b'define([],function(){var Channel=1;});',
            BASE+'/js/wifi/wifi_channel_5g.js':b'define([],function(){var m_Channel=6;});'})
  result=inspect_wifi_channels(SimpleNamespace(base=BASE),opener=o)
  self.assertEqual(result['scan_scope'],'channel_modules')
  self.assertEqual([r['path'] for r in result['files']],
                   ['/js/wifi/wifi_channel.js','/js/wifi/wifi_channel_5g.js'])
  self.assertFalse(result['write_verified'])
  self.assertTrue(all(q.get_method()=='GET' and '/goform' not in q.full_url for q in o.requests))

 def test_pinned_feature_source_fails_closed_on_one_changed_caller(self):
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{}))
  source=b'define(["service"],function(){});'
  path='/js/wifi/wifi_basic.js'
  o=Opener({BASE+path:source})
  with patch.dict(WIFI_FEATURE_PINNED,{path:hashlib.sha256(source).hexdigest()},clear=True):
   result=wifi_feature_source(c,'basic',o)
  self.assertEqual(result['status'],'pinned_static_source_only')
  self.assertEqual(result['files'][0]['source'],source.decode())
  o=Opener({BASE+path:b'changed'})
  with patch.dict(WIFI_FEATURE_PINNED,{path:hashlib.sha256(source).hexdigest()},clear=True):
   result=wifi_feature_source(c,'basic',o)
  self.assertEqual(result['status'],'asset_mismatch')
  self.assertEqual(result['files'],[])
  o=Opener({})
  self.assertEqual(wifi_feature_source(c,'../service',o)['status'],'unsupported_module')
  self.assertFalse(o.requests)
 def test_pinned_service_getter_excerpts_are_bounded_and_get_only(self):
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{}))
  js=b'var api={getWifiAccessPointInfo:function(){return {nv:"wifi_chip1_channel"}},getWifiModuleSwitchStatus:function(){return {nv:"wifi_enabled"}}};'
  o=Opener({BASE+'/js/service.js':js})
  with patch('webui_evidence.SERVICE_SHA256',hashlib.sha256(js).hexdigest()):
   result=wifi_getter_source(c,o)
  self.assertEqual(result['status'],'pinned_static_getters_only')
  self.assertEqual([e['getter'] for e in result['excerpts']],['getWifiAccessPointInfo','getWifiModuleSwitchStatus'])
  self.assertIn('getDfsEaseSetting',result['missing'])
  self.assertTrue(all(q.get_method()=='GET' and q.full_url.endswith('/js/service.js') for q in o.requests))
  self.assertFalse(result['write_verified'])
 def test_service_getter_excerpts_fail_closed_on_changed_asset_and_firmware(self):
  c=SimpleNamespace(base=BASE,query_groups=lambda _:({'device':{'cr_version':'wrong'}},{}))
  o=Opener({})
  self.assertEqual(wifi_getter_source(c,o)['status'],'firmware_mismatch')
  self.assertFalse(o.requests)
  c.query_groups=lambda _:({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'}},{})
  o=Opener({BASE+'/js/service.js':b'getWifiAccessPointInfo:function(){return "UNKNOWN"}'})
  result=wifi_getter_source(c,o)
  self.assertEqual(result['status'],'asset_mismatch')
  self.assertEqual(result['excerpts'],[])
