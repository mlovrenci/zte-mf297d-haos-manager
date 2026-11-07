import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager/src'))
from webui_evidence import inspect, safe_url, MAX_FILE_BYTES
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
