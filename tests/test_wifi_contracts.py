import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager/src'))
from wifi_contracts import catalogue
from zte_api import WIFI_DETAIL_PROBES
class ContractTests(unittest.TestCase):
 def test_secondary_parameters_are_distinct_and_never_sendable(self):
  c=catalogue();self.assertFalse(c['sendable']);self.assertFalse(c['write_verified'])
  self.assertIn('ssid',c['contracts']['SET_WIFI_SSID1_SETTINGS']['fields'])
  self.assertIn('m_SSID',c['contracts']['SET_WIFI_SSID2_SETTINGS']['fields'])
  self.assertNotIn('ssid',c['contracts']['SET_WIFI_SSID2_SETTINGS']['fields'])
  self.assertEqual(c['read_mappings']['guest_ssid']['radio1'],'wifi_chip1_ssid2_ssid')
  self.assertEqual(c['read_mappings']['main_ssid']['radio2'],'wifi_chip2_ssid1_ssid')
  self.assertIn('does not map',c['read_mappings']['note'])
  c['contracts'].clear();self.assertEqual(len(catalogue()['contracts']),3)
 def test_advanced_reads_exclude_secrets(self):
  keys=WIFI_DETAIL_PROBES['b08_advanced']+WIFI_DETAIL_PROBES['b08_advanced_secondary']
  self.assertIn('Channel',keys);self.assertIn('m_wifi_11n_cap',keys)
  self.assertFalse(any(any(word in key.lower() for word in ['password','passphrase','wps','psk']) for key in keys))
 def test_guest_reads_are_original_status_fields_and_secret_free(self):
  keys=WIFI_DETAIL_PROBES['b08_guest']
  self.assertEqual(keys,['wifi_chip1_ssid2_max_access_num','wifi_chip2_ssid2_max_access_num',
                         'm_ssid_enable','m_HideSSID'])
  self.assertFalse(any(word in key.lower() for key in keys for word in ('password','passphrase','psk','wps','pin')))
