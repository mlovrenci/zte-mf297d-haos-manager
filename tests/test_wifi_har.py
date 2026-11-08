import json
import unittest
from tools.analyze_wifi_har import analyze

class HarTests(unittest.TestCase):
    def entry(self, method='GET', body=None):
        return {'request':{'method':method,'url':'http://private-router/goform/goform_get_cmd_process?cmd=Channel,password,session&multi_data=1&token=SECRET', 'cookies':[{'value':'SECRET'}]},
                'response':{'status':200,'content':{'text':json.dumps(body or {'Channel':'PRIVATE_VALUE','password':'SECRET'})}}}
    def test_no_secrets_and_no_replay(self):
        r=analyze({'log':{'entries':[self.entry(),self.entry('POST')]}})
        self.assertFalse(r['sendable']);self.assertTrue(r['offline_only'])
        self.assertEqual(r['reads'][0]['fields'],{'Channel':'present'})
        self.assertEqual(r['reads'][0]['omitted_key_count'],2)
        for value in ['SECRET','PRIVATE_VALUE','private-router','password','session']:
            self.assertNotIn(value,json.dumps(r))
    def test_empty_missing_and_html(self):
        e=self.entry(body={'Channel':''})
        self.assertEqual(analyze({'log':{'entries':[e]}})['reads'][0]['fields']['Channel'],'empty')
        e['response']['content']['text']='<html>login</html>'
        r=analyze({'log':{'entries':[e]}})['reads'][0]
        self.assertEqual(r['response_shape'],'unavailable_or_non_object')
        self.assertEqual(r['fields']['Channel'],'missing')
    def test_invalid_shape(self):
        with self.assertRaises(ValueError): analyze({'log':{'entries':{}}})
