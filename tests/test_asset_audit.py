import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('asset_audit',Path(__file__).resolve().parents[1]/'tools/audit_b08_assets.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
class AssetTests(unittest.TestCase):
 def test_static_inventory_is_not_write_verification(self):
  with tempfile.TemporaryDirectory() as root:
   Path(root,'wifi.js').write_text('const x={goformId:"SET_WIFI_INFO",password:"SECRET"}; wifi_chip1_channel;')
   result=audit.analyze(root)
   self.assertEqual(result['files'][0]['goform_ids'],['SET_WIFI_INFO'])
   self.assertNotIn('SECRET',str(result));self.assertFalse(result['write_verified'])
   self.assertEqual(len(result['files'][0]['sha256']),64)
