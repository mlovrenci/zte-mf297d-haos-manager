"""Wi-Fi radio read-only additions for MF297D Manager 0.5.5."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "zte_manager" / "src"
sys.path.insert(0, str(BASE))
from zte_api import RouterClient, RouterError, WIFI_DETAIL_PROBES


class WifiDiagnosticsTests(unittest.TestCase):
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
