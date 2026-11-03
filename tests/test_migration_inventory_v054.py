"""Regression tests for read-only migration-inventory normalization."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "zte_manager" / "src"))
from migration_inventory import normalize_client, capture_inventory


class FakeClient:
    def __init__(self):
        self.write_calls = 0
    def clients(self):
        return ([{"mac_addr":"AA:BB:CC:DD:EE:02","ip_addr":"192.168.1.5","hostname":"iPhone"}], {})
    def lan_clients(self):
        return [{"mac_addr":"AA:BB:CC:DD:EE:03","ip_addr":"192.168.1.6","hostname":"camera"}]


class MigrationTests(unittest.TestCase):
    def test_valid_client(self):
        v = normalize_client({"mac_addr":"aa:bb:cc:dd:ee:02","ip_addr":"192.168.1.5","hostname":"Phone"}, "wifi")
        self.assertEqual(v["mac"], "AA:BB:CC:DD:EE:02")
    def test_reject_invalid(self):
        self.assertIsNone(normalize_client({"mac":"xx", "ip":"192.168.1.9"}, "wifi"))
        self.assertIsNone(normalize_client({"mac":"AA:BB:CC:DD:EE:03", "ip":"8.8.8.8"}, "wifi"))
    def test_no_write_methods(self):
        import unittest.mock as mock
        with mock.patch("migration_inventory.validated_rows", return_value=[{"mac":"AA:BB:CC:DD:EE:01", "ip":"192.168.1.20", "hostname":"fixed", "domain":"lan"}]):
            result = capture_inventory(FakeClient())
        self.assertEqual(result["reservation_count"], 1)
        self.assertEqual(result["observed_count"], 2)
        self.assertEqual(result["status"], "captured")


if __name__ == "__main__":
    unittest.main()
