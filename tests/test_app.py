import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[1] / "zte_manager" / "src"
sys.path.insert(0, str(BASE))
from zte_api import RouterClient, RouterError, sha
import main

FIRMWARE="CR_A1HRMF297DV1.0.0B08"
GROUPS={
 "device":{"cr_version":FIRMWARE},
 "lan":{"lan_ipaddr":"192.168.1.1","lan_netmask":"255.255.255.0"},
 "dhcp":{"dhcpEnabled":"1","dhcpStart":"192.168.1.100","dhcpEnd":"192.168.1.200","dhcpLease_hour":"24"},
 "wifi":{"wifi_chip1_ssid1_ssid":"Home","wifi_chip1_ssid1_auth_mode":"WPA2PSK","PASSWORD_ENCODE":"0","wifi_chip1_ssid1_max_access_num":"32"},
 "internet":{"BearerPreference":"AUTO","wan_apn":"internet.ht.hr","apn_interface_version":"1"}}
OPTS={"write_enabled":True,"disruptive":False,"apn":False,"firmware":FIRMWARE,"verified_writes":True,"experimental_writes":True,"allow_reboot":False}

class PlanTests(unittest.TestCase):
 def test_dhcp_enabled(self):
  name,params,msg,confirm,watch=main.plan_operation('dhcp',{'enabled':True,'start':'192.168.1.110','end':'192.168.1.211','lease_hours':12},GROUPS,OPTS)
  self.assertEqual(name,'DHCP_SETTING');self.assertEqual(params['lanDhcpType'],'SERVER')
  self.assertEqual(confirm,'POTVRDI')
 def test_disable_requires_explicit_approval(self):
  d={'enabled':False,'start':'192.168.1.100','end':'192.168.1.200','lease_hours':24}
  with self.assertRaises(ValueError):main.plan_operation('dhcp',d,GROUPS,OPTS)
  allowed={**OPTS,'disruptive':True}
  self.assertEqual(main.plan_operation('dhcp',{**d,'recovery_ready':True},GROUPS,allowed)[3],'DHCP_ISKLJUCI')
 def test_subnet_and_gateway(self):
  for begin,end in [('10.10.10.1','10.10.10.4'),('192.168.1.1','192.168.1.200'),('192.168.1.220','192.168.1.210')]:
   with self.assertRaises(ValueError):main.plan_operation('dhcp',{'enabled':True,'start':begin,'end':end,'lease_hours':24},GROUPS,OPTS)
 def test_firmware_fail_closed(self):
  with self.assertRaises(ValueError):main.plan_operation('dhcp',{'enabled':True,'start':'192.168.1.100','end':'192.168.1.200','lease_hours':24},GROUPS,{**OPTS,'firmware':'different'})
 def test_apn_blocked_even_when_options_enabled(self):
  with self.assertRaisesRegex(ValueError,'čeka potvrdu'):
   main.plan_operation('apn',{'apn':'test'},GROUPS,{**OPTS,'apn':True,'disruptive':True})
 def test_wifi_password_encoding_guard(self):
  data={'ssid':'NewSSID','wifi_password':'testpassword123'}
  with self.assertRaises(ValueError): main.plan_operation('wifi_primary',data,GROUPS,OPTS)
  with self.assertRaisesRegex(ValueError,'wifi_password_format'):
   main.plan_operation('wifi_primary',data,GROUPS,{**OPTS,'disruptive':True})
  p=main.plan_operation('wifi_primary',data,GROUPS,{**OPTS,'disruptive':True,'wifi_format':'plain'})
  self.assertEqual(p[1]['ssid'],'NewSSID')
  self.assertEqual(p[1]['passphrase'],'testpassword123')
  p2=main.plan_operation('wifi_primary',data,GROUPS,{**OPTS,'disruptive':True,'wifi_format':'base64'})
  self.assertEqual(p2[1]['passphrase'],'dGVzdHBhc3N3b3JkMTIz')
 def test_bearer_preference_uses_documented_zte_values(self):
  with self.assertRaises(ValueError):main.plan_operation('bearer',{'mode':'AUTO'},GROUPS,{**OPTS,'disruptive':True})
  self.assertEqual(main.plan_operation('bearer',{'mode':'Only_LTE'},GROUPS,{**OPTS,'disruptive':True})[1]['BearerPreference'],'Only_LTE')
 def test_login_hash(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',return_value={'LD':'123abc'}), patch.object(c,'_request',return_value={'result':'0'}) as post:
   c.login('example-test-password')
   _, payload=post.call_args.args
   self.assertEqual(payload['password'],sha(sha('example-test-password')+'123abc'))
 def test_token_hash(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',return_value={'wa_inner_version':'w','cr_version':'c','RD':'r'}):
   self.assertEqual(c._ad(),sha(sha('wc')+'r'))
 def test_set_allowlist(self):
  c=RouterClient('192.168.1.1')
  with self.assertRaises(RouterError): c.set('NOT_ALLOWED',{})

class ClientsRegressionTests(unittest.TestCase):
 def test_station_list_single_key_only(self):
  c = RouterClient('192.168.1.1')
  sample = {'station_list':'[{"hostname":"TV","ip_addr":"192.168.1.20","mac_addr":"AA:BB:CC:DD:EE:FF","ssid_index":"1"}]'}
  def fake_get(fields):
   # Simulates B08: station_list returned in single-key mode,
   # but absent from a request combined with extra metadata fields.
   return sample if fields == ['station_list'] else {}
  with patch.object(c, 'get', side_effect=fake_get) as get:
   clients, details = c.clients()
  self.assertEqual(clients[0]['hostname'], 'TV')
  self.assertEqual(clients[0]['ip_addr'], '192.168.1.20')
  self.assertEqual(details, {})
  get.assert_called_once_with(['station_list'])
 def test_station_list_array(self):
  c = RouterClient('192.168.1.1')
  with patch.object(c, 'get', return_value={'station_list':[{'hostname':'Phone','ip_addr':'192.168.1.25','mac_addr':'11:22','ssid_index':'0'}]}):
   clients, _ = c.clients()
  self.assertEqual(clients[0]['hostname'], 'Phone')
 def test_station_list_missing_is_empty(self):
  c = RouterClient('192.168.1.1')
  with patch.object(c, 'get', return_value={'host_name_web':'TV'}):
   clients, details = c.clients()
  self.assertEqual(clients, [])
  self.assertEqual(details, {})

class FakeClient:
 def __init__(self,*a,**k): pass
 def login(self,*a):self.authenticated=True
 def query_groups(self, selected=None):
  groups={**{k:{} for k in ('device','internet','signal','lan','dhcp','dns','wifi')},**GROUPS}
  return ({k:groups.get(k,{}) for k in selected} if selected is not None else groups),{}
 def clients(self, strict=False):return [],{}
 def lan_clients(self, strict=False):return []
 def wifi_radio_details(self):return {'fields':{'wifi_lbd_enable':'1'},'field_status':{'wifi_lbd_enable':'returned'},'errors':{}}
 def dhcp_inventory(self):return {'fields_present':{},'data':{},'errors':{}}
 def set(self,*args): return {'result':'accepted'}

class HTTPTests(unittest.TestCase):
 def setUp(self):
  self._write_override=main.WRITE_OVERRIDE;main.WRITE_OVERRIDE=None
  self.temp=tempfile.TemporaryDirectory()
  self.options=Path(self.temp.name)/'options.json'
  self.options.write_text(json.dumps({'router_ip':'192.168.1.1','router_password':'test','write_enabled':True,'expected_firmware':FIRMWARE,'allow_disruptive_changes':False,'allow_apn_changes':False,'b08_write_verified':True,'allow_experimental_writes':True}))
  self._a=main.OPTIONS;main.OPTIONS=self.options
  self._b=main.AUDIT;main.AUDIT=Path(self.temp.name)/'audit'
  self.server=ThreadingHTTPServer(('127.0.0.1',0),main.Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
  self.thread.start()
  self.mock=patch.object(main,'RouterClient',FakeClient);self.mock.start()
  self.addr=f'http://127.0.0.1:{self.server.server_address[1]}'
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join(2)
  self.mock.stop();main.OPTIONS=self._a;main.AUDIT=self._b
  main.WRITE_OVERRIDE=self._write_override
  self.temp.cleanup()
 def fetch(self,path,body=None,headers=None):
  req=Request(self.addr+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
  if body is not None:req.add_header('Content-Type','application/json')
  with urlopen(req,timeout=5) as r:return json.loads(r.read())
 def test_meta_state(self):
  self.assertEqual(self.fetch('/api/meta')['version'],'0.6.0')
  self.assertEqual(self.fetch('/api/state')['groups']['device']['cr_version'],FIRMWARE)
 def test_studio_and_live_routes(self):
  for path, marker in [("/", b"preview.js"), ("/index.html", b"preview.js"), ("/demo", b"connect-src"), ("/live", b"writeModeToggle"), ("/static/studio.js", b"ZteDemo.create"), ("/static/dev-model.js", b"const ZteDemo")]:
   with urlopen(self.addr+path,timeout=5) as response:
    self.assertIn(marker,response.read())
 def test_preview_snapshot_cannot_write_or_create_plan(self):
  plans=dict(main.PLANS)
  with patch.object(FakeClient,'set',side_effect=AssertionError('router write')) as write:
   result=self.fetch('/api/preview_snapshot')
  write.assert_not_called()
  self.assertFalse(result['write_available'])
  self.assertEqual(result['groups']['device']['cr_version'],FIRMWARE)
  self.assertEqual(main.PLANS,plans)
  self.assertFalse(result['clients_error'])
 def test_preview_clients_error_is_not_empty_success(self):
  with patch.object(FakeClient,'clients',side_effect=RouterError('offline')):
   result=self.fetch('/api/preview_snapshot')
  self.assertTrue(result['clients_error'])
  self.assertEqual(result['groups']['wifi']['wifi_chip1_ssid1_ssid'],'Home')
 def test_preview_reservations_are_read_only(self):
  with patch.object(FakeClient,'get',return_value={'current_static_addr_list':[]},create=True), patch.object(FakeClient,'set',side_effect=AssertionError('write')) as write:
   result=self.fetch('/api/preview_reservations')
  write.assert_not_called()
  self.assertEqual(result['status'],'empty_or_unsupported')
  self.assertFalse(result['write_available'])
 def test_wifi_view_asset_served(self):
  with urlopen(self.addr+'/static/wifi-view.js',timeout=5) as response:
   self.assertIn('application/javascript',response.headers['Content-Type'])
   self.assertIn(b'const WifiView',response.read())
 def test_wifi_details_is_read_only(self):
  response=self.fetch('/api/wifi_details')
  self.assertEqual(response['fields']['wifi_lbd_enable'],'1')
  self.assertEqual(response['clients'],[])
 def test_wifi_details_retains_radio_if_station_list_fails(self):
  with patch.object(FakeClient,'clients',side_effect=RouterError('station_list unavailable')):
   response=self.fetch('/api/wifi_details')
  self.assertEqual(response['fields']['wifi_lbd_enable'],'1')
  self.assertEqual(response['errors']['clients'],'read_unavailable')
 def test_write_mode_switch_is_local_and_invalidates_plans(self):
  h={'X-ZTE-Action':'yes','X-ZTE-CSRF':main.CSRF}
  before=self.options.read_bytes()
  main.PLANS['old']={};main.STATIC_PLANS['old']={}
  with patch.object(main,'connect') as connect:
   result=self.fetch('/api/write_mode',{'enabled':False},h)
   self.assertFalse(result['write_enabled'])
   self.assertFalse(main.options()['write_enabled'])
   self.assertFalse(main.PLANS);self.assertFalse(main.STATIC_PLANS)
   for endpoint in ('prepare','apply','static_prepare','static_apply'):
    with self.assertRaises(HTTPError):self.fetch('/api/'+endpoint,{},h)
   self.assertTrue(self.fetch('/api/write_mode',{'enabled':True},h)['write_enabled'])
   connect.assert_not_called()
  self.assertEqual(self.options.read_bytes(),before)
  self.assertFalse(main.options()['disruptive'])
  self.assertFalse(main.options()['allow_reboot'])
 def test_write_mode_requires_csrf_and_boolean(self):
  with self.assertRaises(HTTPError) as err:self.fetch('/api/write_mode',{'enabled':True})
  self.assertEqual(err.exception.code,403)
  h={'X-ZTE-Action':'yes','X-ZTE-CSRF':main.CSRF}
  with self.assertRaises(HTTPError):self.fetch('/api/write_mode',{'enabled':'true'},h)
  self.assertIsNone(main.WRITE_OVERRIDE)
 def test_write_mode_overrides_locked_config_without_persisting(self):
  h={'X-ZTE-Action':'yes','X-ZTE-CSRF':main.CSRF}
  config=json.loads(self.options.read_text());config['write_enabled']=False;config['allow_experimental_writes']=False
  self.options.write_text(json.dumps(config))
  self.fetch('/api/write_mode',{'enabled':True},h)
  self.assertTrue(main.options()['write_enabled']);self.assertTrue(main.options()['experimental_writes'])
  main.WRITE_OVERRIDE=None
  self.assertFalse(main.options()['write_enabled']);self.assertFalse(main.options()['experimental_writes'])
 def test_requires_header(self):
  with self.assertRaises(HTTPError) as err:
   self.fetch('/api/prepare',{'operation':'dhcp','values':{}})
  self.assertEqual(err.exception.code,403)
 def test_prepare_and_apply(self):
  h={'X-ZTE-Action':'yes','X-ZTE-CSRF':main.CSRF}
  p=self.fetch('/api/prepare',{'operation':'dhcp','values':{'enabled':True,'start':'192.168.1.100','end':'192.168.1.200','lease_hours':24}},h)
  self.assertIn('plan_id',p)
  with self.assertRaises(HTTPError):self.fetch('/api/apply',{'plan_id':p['plan_id'],'confirmation':'wrong'},h)
  # One-time token was consumed; replay must fail.
  with self.assertRaises(HTTPError):self.fetch('/api/apply',{'plan_id':p['plan_id'],'confirmation':'POTVRDI'},h)
  p=self.fetch('/api/prepare',{'operation':'dhcp','values':{'enabled':True,'start':'192.168.1.100','end':'192.168.1.200','lease_hours':24}},h)
  self.assertEqual(self.fetch('/api/apply',{'plan_id':p['plan_id'],'confirmation':'POTVRDI'},h)['status'],'sent')

if __name__=='__main__': unittest.main()

# Additional v0.3 regression coverage (unittest discovery executes this class too).
class V03Tests(unittest.TestCase):
 def test_unverified_write_denied_even_if_enabled(self):
  vals={'enabled':True,'start':'192.168.1.120','end':'192.168.1.200','lease_hours':24}
  with self.assertRaisesRegex(ValueError,'zaključan'):
   main.plan_operation('dhcp',vals,GROUPS,{**OPTS,'experimental_writes':False})
 def test_availability_is_not_a_write_claim(self):
  caps=main.capabilities({**GROUPS,'traffic':{'realtime_rx_thrp':'0'}})
  self.assertEqual(caps['dhcp']['status'],'available')
  self.assertEqual(caps['traffic']['status'],'available')
  self.assertFalse(caps['dhcp']['firmware_verified'])
 def test_history_has_no_sensitive_ids(self):
  temp=tempfile.TemporaryDirectory()
  old=main.HISTORY
  main.HISTORY=Path(temp.name)/'history.sqlite'
  try:
   groups={'signal':{'lte_rsrp':'-95 dBm','lte_rsrq':'-7','lte_snr':'14.5','cell_id':'cell 123'},
           'traffic':{'realtime_rx_thrp':'65432','realtime_tx_thrp':'234'},
           'internet':{'ppp_status':'ppp_connected','network_provider':'HT','imsi':'should-not-store','imei':'also-not'}}
   main.record_sample(groups)
   rows=main.read_history(24)
   self.assertEqual(len(rows),1)
   self.assertEqual(rows[0]['rsrp'],-95)
   self.assertEqual(rows[0]['down'],65432)
   self.assertNotIn('imsi',rows[0]);self.assertNotIn('imei',rows[0])
  finally:
   main.HISTORY=old
   temp.cleanup()
 def test_multi_group_scoped_monitor(self):
  client=RouterClient('192.168.1.1')
  with patch.object(client,'get',return_value={}) as getter:
   groups,_=client.query_groups(['signal','traffic'])
  self.assertEqual(set(groups),{'signal','traffic'})
  self.assertEqual(getter.call_count,2)
 def test_sensitive_fields_not_queried(self):
  from zte_api import GROUPS
  keys=','.join(x for group in GROUPS.values() for x in group).lower()
  for sensitive in ('imsi','imei','passphrase','sms_body','sim_pin','wifi_chip1_ssid1_password,','wifi_chip2_ssid1_password,'):
   self.assertNotIn(sensitive,keys)


class B08ObservedResponseTests(unittest.TestCase):
 def test_real_diagnostic_traffic_counters_not_missing(self):
  groups={
   'traffic': {'realtime_tx_bytes':'0', 'realtime_rx_bytes':'0', 'monthly_tx_bytes':'124', 'monthly_rx_bytes':'234', 'total_tx_bytes':'22', 'total_rx_bytes':'33', 'monthly_time':'10'},
   'system_extra': {'sntp_time_set_mode':'auto', 'sntp_timezone':'1'},
   'dns': {'dns_mode':'auto'},
   'network_extra': {},
  }
  caps=main.capabilities(groups)
  self.assertEqual(caps['traffic']['status'], 'partial')
  self.assertEqual(caps['system']['status'], 'partial')
  self.assertEqual(caps['dns']['status'], 'available')
  self.assertEqual(caps['nat']['status'], 'not_returned')
  self.assertIn('realtime_rx_bytes', caps['traffic']['fields'])
  self.assertIn('sntp_timezone', caps['system']['fields'])
  self.assertFalse(caps['traffic']['firmware_verified'])

 def test_correct_zte_throughput_field_names(self):
  from zte_api import GROUPS
  self.assertIn('realtime_rx_thrpt', GROUPS['traffic'])
  self.assertIn('realtime_tx_thrpt', GROUPS['traffic'])
  caps=main.capabilities({'traffic': {'realtime_rx_thrpt': '520', 'monthly_rx_bytes':'123'}})
  self.assertEqual(caps['traffic']['status'], 'available')
  self.assertIn('realtime_rx_thrpt', caps['traffic']['fields'])

 def test_monitor_accepts_documented_thrpt_fields(self):
  tmp=tempfile.TemporaryDirectory(); orig=main.HISTORY
  main.HISTORY=Path(tmp.name)/'samples.db'
  try:
   main.record_sample({'traffic':{'realtime_rx_thrpt':'4321', 'realtime_tx_thrpt':'456'}, 'signal':{}, 'internet':{}})
   samples=main.read_history(24)
   self.assertEqual(samples[0]['down'],4321)
   self.assertEqual(samples[0]['up'],456)
  finally:
   main.HISTORY=orig; tmp.cleanup()

 def test_diagnostic_network_values_explicit_allowlist_only(self):
  groups={
    'lan':{'lan_ipaddr':'192.168.1.1','lan_netmask':'255.255.255.0','mac_address':'TOPSECRET'},
    'dhcp':{'dhcpEnabled':'1','dhcpStart':'192.168.1.100','dhcpEnd':'192.168.1.200','dhcpLease_hour':'24'},
    'dns':{'dns_mode':'auto','password':'NEVER'},
    'internet':{'wan_apn':'private','imsi':'sensitive'},
  }
  snapshot=main.sanitized_network_snapshot(groups)
  self.assertEqual(snapshot['dhcp']['dhcpStart'],'192.168.1.100')
  serialized=json.dumps(snapshot)
  for sensitive in ('TOPSECRET','NEVER','sensitive','private'):
   self.assertNotIn(sensitive,serialized)
  self.assertEqual(set(snapshot),{'lan','dhcp','dns'})


class FullControlV04Tests(unittest.TestCase):
 def test_dhcp_lease_in_seconds_from_b08_snapshot(self):
  p=main.plan_operation('dhcp',{'enabled':True,'start':'192.168.1.100','end':'192.168.1.200','lease_hours':24},GROUPS,OPTS)
  self.assertEqual(p[1]['dhcpLease'],'86400')
 def test_wan_dial_requires_permission_and_status(self):
  with self.assertRaises(ValueError):main.plan_operation('wan_connection',{'mode':'auto_dial'},GROUPS,OPTS)
  g={**GROUPS,'internet':{**GROUPS['internet'],'ppp_status':'ppp_connected'}}
  p=main.plan_operation('wan_connection',{'mode':'auto_dial'},g,{**OPTS,'disruptive':True})
  self.assertEqual(p[0],'SET_CONNECTION_MODE')
 def test_upnp_cannot_be_changed_without_read_support(self):
  g={**GROUPS,'network_extra':{}}
  with self.assertRaisesRegex(ValueError,'nije vraćen'):
   main.plan_operation('upnp',{'enabled':False},g,{**OPTS,'disruptive':True})
 def test_dmz_never_targets_gateway(self):
  g={**GROUPS,'network_extra':{'DMZEnable':'0','DMZIPAddress':'192.168.1.100'}}
  with self.assertRaisesRegex(ValueError,'gateway'):
   main.plan_operation('dmz',{'enabled':True,'address':'192.168.1.1'},g,{**OPTS,'disruptive':True})
  p=main.plan_operation('dmz',{'enabled':False},g,{**OPTS,'disruptive':True})
  self.assertEqual(p[1]['DMZEnabled'],'0')
 def test_reboot_is_separately_gated(self):
  with self.assertRaises(ValueError):main.plan_operation('reboot',{},GROUPS,{**OPTS,'disruptive':True})
  p=main.plan_operation('reboot',{},GROUPS,{**OPTS,'disruptive':True,'allow_reboot':True})
  self.assertEqual(p[0],'REBOOT_DEVICE')
 def test_sensitive_wifi_password_not_sent_on_read(self):
  from zte_api import GROUPS as G
  self.assertNotIn('wifi_chip1_ssid1_password_encode',G['wifi_extra'])
 def test_lan_clients_single_key(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',return_value={'lan_station_list':'[{"hostname":"Beelink","ip_addr":"192.168.1.10","mac_addr":"FF"}]'}) as q:
   self.assertEqual(c.lan_clients()[0]['hostname'],'Beelink')
  q.assert_called_once_with(['lan_station_list'])

class DHCPInventoryTests(unittest.TestCase):
 def test_safe_read_inventory(self):
  c=RouterClient('192.168.1.1')
  def mocked(keys):
   k=keys[0]
   return {k: '[{"mac_addr":"AA:BB:CC:DD:EE:FF","ip_addr":"192.168.1.12","secret":"do-not-leak"}]'} if k=='current_static_addr_list' else ({k:'192.168.1.10'} if k=='dhcp_dns1' else {})
  with patch.object(c,'get',side_effect=mocked):
   d=c.dhcp_inventory()
  self.assertEqual(d['data']['reservations']['current_static_addr_list'][0]['ip_addr'],'192.168.1.12')
  self.assertNotIn('secret',str(d))
  self.assertEqual(d['data']['dhcp_client_dns']['dhcp_dns1'],'192.168.1.10')

class DHCPInventoryV041Tests(unittest.TestCase):
 def test_empty_list_key_is_not_discarded(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',side_effect=lambda f: {'current_static_addr_list': '[]'} if f==['current_static_addr_list'] else {}):
   res=c.dhcp_inventory()
  self.assertIn('current_static_addr_list',res['fields_present']['reservations'])
  self.assertEqual(res['field_status']['reservations']['current_static_addr_list'],'returned_empty_list')
  self.assertEqual(res['data']['reservations']['current_static_addr_list'],[])
 def test_missing_key_is_distinct_from_empty_list(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',return_value={}):
   res=c.dhcp_inventory()
  self.assertEqual(res['field_status']['reservations']['current_static_addr_list'],'not_returned')
  self.assertNotIn('current_static_addr_list',res['fields_present']['reservations'])
 def test_populated_entries_cleaned(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',side_effect=lambda f: {'current_static_addr_list': '[{"hostname":"server","mac":"AA:BB","ip":"192.168.1.18","secret":"password"}]'} if f==['current_static_addr_list'] else {}):
   res=c.dhcp_inventory()
  self.assertEqual(res['field_status']['reservations']['current_static_addr_list'],'populated')
  self.assertEqual(res['data']['reservations']['current_static_addr_list'][0]['ip'],'192.168.1.18')
  self.assertNotIn('secret',res['data']['reservations']['current_static_addr_list'][0])
 def test_client_metadata_never_shows_raw_values(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',side_effect=lambda f: {'hostNameList':'SECRET_DATA'} if f==['hostNameList'] else {}):
   res=c.dhcp_inventory()
  self.assertNotIn('SECRET_DATA',json.dumps(res))
 def test_empty_dns_string_distinct_from_missing(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c,'get',side_effect=lambda f: {'dhcp_dns1':''} if f==['dhcp_dns1'] else {}):
   res=c.dhcp_inventory()
  self.assertEqual(res['field_status']['dhcp_client_dns']['dhcp_dns1'],'returned_empty')

class ReservationTransportTests(unittest.TestCase):
 def test_get_returns_empty_list(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c, '_request', return_value={'current_static_addr_list': '[]'}) as req:
   result=c.probe_reservation_transport()
  self.assertEqual(result['get']['status'], 'field_present_empty')
  self.assertEqual(result['post_read']['list_length'], 0)
  self.assertEqual(req.call_count, 2)
  self.assertIn('goform_get_cmd_process', req.call_args_list[1].args[0])
 def test_missing_field_and_error_key(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c, '_request', return_value={'result':'failure'}):
   result=c.probe_reservation_transport()
  self.assertEqual(result['get']['status'], 'field_absent')
  self.assertTrue(result['post_read']['result_key_present'])
  self.assertNotIn('failure', str(result))
 def test_post_read_can_work_when_get_fails(self):
  c=RouterClient('192.168.1.1')
  with patch.object(c, '_request', side_effect=[RouterError('test'),{'current_static_addr_list':[{'mac':'ab','ip':'192.168.1.2'}]}]):
   result=c.probe_reservation_transport()
  self.assertEqual(result['get']['status'],'request_error')
  self.assertEqual(result['post_read']['status'],'field_present_nonempty')
  self.assertEqual(result['post_read']['list_length'],1)
  self.assertNotIn('192.168.1.2',str(result))
  self.assertNotIn('ab',str(result))
 def test_both_requests_only_use_read_endpoint(self):
  c=RouterClient('192.168.1.1')
  sent=[]
  def fake_request(url, form=None):
   sent.append((url,form));return {'current_static_addr_list': []}
  with patch.object(c, '_request',side_effect=fake_request): c.probe_reservation_transport()
  self.assertEqual(len(sent),2)
  self.assertTrue(all('goform_get_cmd_process' in url and 'goform_set_cmd_process' not in url for url,_ in sent))

