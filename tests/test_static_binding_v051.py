import sys, unittest, tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager'/'src'))
import static_binding_test as st

class FakeRouter:
 def __init__(self, rows=None, response='success'):
  self.rows=list(rows or [{'hostname':f'h{i}', 'mac':f'00:00:00:00:00:{i:02X}', 'ip':f'192.168.1.{20+i}', 'domain':''} for i in range(9)])
  self.response=response
  self.writes=[]
 def query_groups(self, selected=None):
  return ({'device':{'cr_version':'CR_A1HRMF297DV1.0.0B08'},'lan':{'lan_ipaddr':'192.168.1.1','lan_netmask':'255.255.255.0'},'dhcp':{'dhcpEnabled':'1','dhcpStart':'192.168.1.2','dhcpEnd':'192.168.1.253'}}, {})
 def probe_reservation_transport(self, include_records=False):
  return {'get':{'status':'field_present_nonempty','value_type':'list','list_length':len(self.rows),'records':list(self.rows)}}
 def _ad(self):return 'dummy-token-test-only'
 def _request(self,path,data):
  self.writes.append(data)
  if data['goformId']=='DHCP_RESERVATION_ADD':
   self.rows.append({'hostname':data['host_name'],'mac':data['mac_addr'],'ip':data['ip_addr'],'domain':data['domain']})
  if data['goformId']=='DHCP_RESERVATION_DEL':
   self.rows[:]=[x for x in self.rows if x['mac']!=st.MAC]
  return {'result': self.response}

class Tests(unittest.TestCase):
 def test_successful_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter();report=st.run_binding_test(lambda:fake, Path(d)/'test.json')
   self.assertEqual('passed',report['status'])
   self.assertEqual(9, report['before_count'])
   self.assertEqual(10,report['after_add_count'])
   self.assertEqual(9,report['final_count'])
   self.assertEqual(['DHCP_RESERVATION_ADD','DHCP_RESERVATION_DEL'],[x['goformId'] for x in fake.writes])
   self.assertEqual(st.MAC+';',fake.writes[1]['mac_addr'])
 def test_never_reruns_after_marker(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter();marker=Path(d)/'test.json'
   st.run_binding_test(lambda:fake,marker)
   with self.assertRaises(st.StaticTestError):st.run_binding_test(lambda:fake,marker)
 def test_existing_ip_never_written(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter(rows=[{'mac':'aa:bb:cc:dd:ee:ff','ip':st.IP}]);report=st.run_binding_test(lambda:fake,Path(d)/'test.json')
   self.assertEqual('aborted',report['status']);self.assertEqual([],fake.writes)
 def test_unexpected_lan_never_written(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter();orig=fake.query_groups
   def altered(*args,**kwargs):
    v,e=orig();v['lan']['lan_ipaddr']='192.168.3.1';return v,e
   fake.query_groups=altered
   report=st.run_binding_test(lambda:fake,Path(d)/'test.json')
   self.assertEqual('aborted',report['status']);self.assertEqual([],fake.writes)
 def test_only_dummy_mac_deleted(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter();original=list(fake.rows)
   report=st.run_binding_test(lambda:fake,Path(d)/'test.json')
   self.assertEqual(original,fake.rows)
   self.assertEqual(st.MAC+';',fake.writes[1]['mac_addr'])
 def test_api_parameters_match_original_webui(self):
  fake=FakeRouter()
  st._send_binding(fake,'add');st._send_binding(fake,'delete')
  self.assertEqual({'host_name','mac_addr','ip_addr','domain','AD','goformId','isTest'},set(fake.writes[0]))
  self.assertEqual({'mac_addr','AD','goformId','isTest'},set(fake.writes[1]))
  self.assertEqual(st.IP,fake.writes[0]['ip_addr'])
 def test_failed_delete_reports_cleanup(self):
  with tempfile.TemporaryDirectory() as d:
   fake=FakeRouter();orig=fake._request
   def fail_delete(path,data):
    if data['goformId']=='DHCP_RESERVATION_DEL':raise st.StaticTestError('denied')
    return orig(path,data)
   fake._request=fail_delete
   report=st.run_binding_test(lambda:fake,Path(d)/'test.json')
   self.assertEqual('cleanup_needed',report['status'])
   self.assertTrue(report['observed_after_add'])
 def test_packet_length_limit(self):
  from mqtt_probe import _packet
  self.assertEqual(b'\xc0\x00',_packet(0xc0,b''))

if __name__=='__main__': unittest.main()