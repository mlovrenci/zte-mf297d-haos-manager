"""Wi-Fi radio read-only additions for MF297D Manager 0.5.5."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "zte_manager" / "src"
sys.path.insert(0, str(BASE))
from zte_api import RouterClient, RouterError, WIFI_DETAIL_PROBES


class WifiDiagnosticsTests(unittest.TestCase):
    def test_original_b08_radio_gets_only_two_pinned_queries_and_scrubs_secrets(self):
        client = RouterClient("192.168.1.1")
        calls=[]
        def fake_get(keys):
            calls.append(keys)
            if keys == ['cr_version', 'wa_inner_version', 'hardware_version', 'web_version', 'Language']:
                return {'cr_version':'CR_A1HRMF297DV1.0.0B08'}
            if keys == ['queryWiFiChipAdvancedInfo']:
                return {'ResponseList':[{'ChipIndex':'0','Channel':'6','BandWidth':'40',
                                          'Password':'SECRET','SSID':'PRIVATE','Unknown':'HIDE'},
                                         {'ChipIndex':'1','Channel':'36','BandWidth':'80'}]}
            if keys == ['queryWiFiModuleSwitch']:
                return {'WiFiModuleSwitch':'3','password':'SECRET'}
            raise AssertionError('Unexpected query')
        with patch.object(client,'get',side_effect=fake_get), patch.object(client,'set',side_effect=AssertionError('router write')):
            result=client.wifi_original_radio_read()
        self.assertEqual([x[0] for x in calls[1:]],['queryWiFiChipAdvancedInfo','queryWiFiModuleSwitch'])
        self.assertEqual(result['radio_status'],'observed')
        self.assertEqual(result['radios'][0]['fields'],{'ChipIndex':'0','Channel':'6','BandWidth':'40'})
        self.assertEqual(result['module'],{'WiFiModuleSwitch':'3'})
        self.assertNotIn('SECRET',str(result));self.assertNotIn('PRIVATE',str(result))
        self.assertFalse(result['write_available'])

    def test_original_b08_radio_firmware_mismatch_never_probes(self):
        client=RouterClient('192.168.1.1')
        with patch.object(client,'get',return_value={'cr_version':'other'}) as get:
            result=client.wifi_original_radio_read()
        self.assertEqual(result['status'],'firmware_mismatch')
        self.assertEqual(get.call_count,1)

    def test_original_b08_radio_malformed_response_does_not_leak(self):
        client=RouterClient('192.168.1.1')
        def fake_get(keys):
            if 'cr_version' in keys:return {'cr_version':'CR_A1HRMF297DV1.0.0B08'}
            if keys==['queryWiFiChipAdvancedInfo']:return {'ResponseList':'not JSON SECRET'}
            if keys==['queryWiFiModuleSwitch']:return {'WiFiModuleSwitch':{'password':'SECRET'}}
            raise AssertionError()
        with patch.object(client,'get',side_effect=fake_get):
            result=client.wifi_original_radio_read()
        self.assertEqual(result['radio_status'],'read_unavailable')
        self.assertEqual(result['switch_status'],'unsupported_or_missing')
        self.assertNotIn('SECRET',str(result))

    def test_only_allowlisted_reads_no_writes(self):
        client = RouterClient("192.168.1.1")
        observed = []

        def mock_get(keys):
            observed.append(keys)
            if keys == WIFI_DETAIL_PROBES["steering"]:
                return {"wifi_lbd_enable": "1", "wifi_dfs_status": "0", "wifi_password": "secret"}
            if keys == WIFI_DETAIL_PROBES["channels"]:
                return {"wifi_chip1_channel": "6", "wifi_chip2_bandwidth": "80"}
            return {"wifi_chip1_ssid2_access_sta_num": "2"}

        with patch.object(client, "get", side_effect=mock_get), patch.object(client, "set") as write:
            result = client.wifi_radio_details()
        self.assertEqual(observed, list(WIFI_DETAIL_PROBES.values()))
        write.assert_not_called()
        self.assertEqual(result["fields"]["wifi_lbd_enable"], "1")
        self.assertEqual(result["fields"]["wifi_chip1_channel"], "6")
        self.assertEqual(result["field_status"]["wifi_chip2_channel"], "not_returned")
        self.assertNotIn("wifi_password", result["fields"])
        self.assertEqual(result["errors"], {})

    def test_radio_error_is_independent(self):
        client = RouterClient("192.168.1.1")

        def mock_get(keys):
            if keys == WIFI_DETAIL_PROBES["channels"]:
                raise RouterError("firmware unknown")
            return {"wifi_lbd_enable": "1"}

        with patch.object(client, "get", side_effect=mock_get):
            result = client.wifi_radio_details()
        self.assertEqual(result["fields"], {"wifi_lbd_enable": "1"})
        self.assertEqual(result["errors"], {"channels": "read_unavailable"})

    def test_client_metrics_only_when_reported_and_safe(self):
        client = RouterClient("192.168.1.1")
        station = [
            {"hostname": "TV", "ssid_index": 0, "rssi": -64, "rx_rate": 150,
             "wifi_password": "not allowed", "signal": {"unexpected": "json"}},
            {"hostname": "Phone", "ssid_index": "1", "tx_rate": "a" * 50},
        ]
        with patch.object(client, "get", return_value={"station_list": station}) as get:
            clients, _ = client.clients()
        get.assert_called_once_with(["station_list"])
        self.assertEqual(clients[0]["ssid_index"], 0)
        self.assertEqual(clients[0]["rssi"], -64)
        self.assertEqual(clients[0]["rx_rate"], 150)
        self.assertNotIn("signal", clients[0])
        self.assertNotIn("wifi_password", clients[0])
        self.assertNotIn("tx_rate", clients[1])


if __name__ == "__main__":
    unittest.main()
