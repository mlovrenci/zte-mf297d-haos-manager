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
  c['contracts'].clear();self.assertEqual(len(catalogue()['contracts']),3)
 def test_advanced_reads_exclude_secrets(self):
  keys=WIFI_DETAIL_PROBES['b08_advanced']+WIFI_DETAIL_PROBES['b08_advanced_secondary']
  self.assertIn('Channel',keys);self.assertIn('m_wifi_11n_cap',keys)
  self.assertFalse(any(any(word in key.lower() for word in ['password','passphrase','wps','psk']) for key in keys))
