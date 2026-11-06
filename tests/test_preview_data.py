import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager'/'src'))
from preview_data import collect, reservations
from zte_api import RouterClient, RouterError

class PreviewTests(unittest.TestCase):
 def client(self):
  c=Mock();c.query_groups.return_value=({'device':{}},{'wifi':'sensitive text'})
  c.wifi_radio_details.return_value={'fields':{},'errors':{}}
  c.clients.return_value=([],{});c.lan_clients.return_value=[]
  c.set.side_effect=AssertionError('writes forbidden')
  return c
 def test_sources_fail_independently_and_errors_are_sanitized(self):
  c=self.client();c.clients.side_effect=RouterError('secret')
  data=collect(c)
  self.assertEqual(data['sources']['wifi']['status'],'unavailable')
  self.assertEqual(data['sources']['lan']['status'],'ok')
  self.assertEqual(data['errors'],{'wifi':'read_unavailable'})
  c.set.assert_not_called()
 def test_reservations_unknown_empty_malformed_and_rows(self):
  for reply,status in [({},'unsupported_or_missing'),({'current_static_addr_list':''},'empty_or_unsupported'),({'current_static_addr_list':'[]'},'empty_or_unsupported'),({'current_static_addr_list':'<html>'},'unavailable'),({'current_static_addr_list':[{'mac':'ab','password':'SECRET'}]},'observed_unverified')]:
   c=self.client();c.get.return_value=reply;result=reservations(c)
   self.assertEqual(result['status'],status);self.assertNotIn('SECRET',str(result));self.assertFalse(result['write_available']);c.set.assert_not_called()
 def test_strict_clients_reject_missing_malformed_source(self):
  for method,key in [('clients','station_list'),('lan_clients','lan_station_list')]:
   c=RouterClient('192.0.2.1')
   for raw in [{},{key:'broken'},{key:{}}]:
    with patch.object(c,'get',return_value=raw):
     with self.assertRaises(RouterError):getattr(c,method)(strict=True)
   with patch.object(c,'get',return_value={key:[]}):
    self.assertIn(getattr(c,method)(strict=True),[[],([],{})])
