import importlib
import io
import json
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / 'zte_manager' / 'src'
sys.path.insert(0, str(BASE))
import main
import mqtt_probe


def read_packet(conn):
    first=conn.recv(1)[0]
    multiplier=1
    remaining=0
    while True:
        value=conn.recv(1)[0]
        remaining += (value & 127)*multiplier
        multiplier *= 128
        if not (value & 128): break
    payload=b''
    while len(payload)<remaining:
        d=conn.recv(remaining-len(payload))
        if not d:break
        payload += d
    return first,payload


class MQTTTests(unittest.TestCase):
    def test_summary_prioritizes_recovered_nonempty(self):
        details={'transport_probe': {'get':{'status':'field_present_empty','list_length':0},'post_read':{'status':'field_present_nonempty','value_type':'list','list_length':2}},
                 'field_status':{'reservations':{'current_static_addr_list':'error'},'dhcp_client_dns':{'lan_dns1':'returned_empty'}},'errors':{}}
        summary=main.summarize_dhcp_probe(details)
        self.assertEqual(summary['status'],'recovered_nonempty')
        self.assertEqual(summary['transport_probe']['post_read']['list_length'],2)
        self.assertNotIn('router_password',json.dumps(summary))
    def test_no_data_summary(self):
        self.assertEqual(main.summarize_dhcp_probe({'transport_probe':{}})['status'],'unconfirmed')
    def test_optional_settings(self):
        self.assertIn('mqtt_diagnostics_enabled: false',(BASE.parent/'config.yaml').read_text())
        self.assertIn('mqtt:want',(BASE.parent/'config.yaml').read_text())
        self.assertNotIn('homeassistant_api: true',(BASE.parent/'config.yaml').read_text())
    def test_tcp_mqtt_publishes_discovery_and_summary(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        addr=listener.getsockname()
        result=[]
        def broker():
            try:
                conn,_=listener.accept()
                with conn:
                    conn.settimeout(5)
                    result.append(read_packet(conn))
                    conn.sendall(b'\x20\x02\x00\x00')
                    for _ in range(3):result.append(read_packet(conn))
                    result.append(read_packet(conn))
            finally:listener.close()
        t=threading.Thread(target=broker)
        t.start()
        try:
            mqtt_probe._mqtt_publish({'host':'127.0.0.1','port':addr[1],'username':'testuser','password':'TESTPASSWORD'},[
                (mqtt_probe.CONFIG_TOPIC,{'name':'Probe','no_secrets':True},True),
                (mqtt_probe.ATTRS_TOPIC,{'status':'recovered_empty'},True),
                (mqtt_probe.STATE_TOPIC,'recovered_empty',True)])
        finally:t.join(3)
        self.assertFalse(t.is_alive())
        self.assertEqual(result[0][0],0x10)
        self.assertEqual([x[0] for x in result[1:4]],[0x31,0x31,0x31])
        self.assertEqual(result[4][0],0xe0)
        self.assertNotIn(b'TESTPASSWORD',b''.join(p for _,p in result[1:]))

if __name__=='__main__':unittest.main()