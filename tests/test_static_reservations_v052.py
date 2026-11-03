import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'zte_manager'/'src'))
import static_reservations as mod

class Router:
    def __init__(self):
        self.rows=[{'mac':f'02:AA:BB:CC:DD:{i:02X}', 'ip':f'192.168.1.{40+i}', 'hostname':f'host{i}', 'domain':''} for i in range(1,10)]
        self.sent=[]
    def query_groups(self,selected=None):
        return ({'device':{'cr_version':mod.FW},'lan':{'lan_ipaddr':'192.168.1.1','lan_netmask':'255.255.255.0'},'dhcp':{'dhcpEnabled':'1'}},{})
    def probe_reservation_transport(self,include_records=False):
        return {'get':{'status':'field_present_nonempty','value_type':'list','list_length':len(self.rows),'records':list(self.rows)}}
    def _ad(self):return 'test_ad'
    def _request(self,path,params):
        self.sent.append(params)
        if params['goformId']=='DHCP_RESERVATION_ADD':
            self.rows.append({'hostname':params['host_name'],'mac':params['mac_addr'],'ip':params['ip_addr'],'domain':params['domain']})
        elif params['goformId']=='DHCP_RESERVATION_DEL':
            mac=params['mac_addr'].rstrip(';')
            self.rows=[r for r in self.rows if r['mac']!=mac]
        return {'result':'success'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.router=Router();self.groups=self.router.query_groups()[0];self.rows=mod.validated_rows(self.router)
    def payload(self):
        return {'mac':'02:12:34:56:78:9A','ip':'192.168.1.100','hostname':'printer_1','domain':'local'}
    def test_add_verified(self):
        p=mod.prepare('add',self.payload(),self.groups,self.rows)
        self.assertEqual('DODAJ_REZERVACIJU',p['confirm'])
        r=mod.execute(self.router,p,self.groups,mod.validated_rows(self.router))
        self.assertEqual('verified',r['status']);self.assertEqual(10,r['after_count'])
        self.assertEqual('DHCP_RESERVATION_ADD',self.router.sent[0]['goformId'])
    def test_delete_verified(self):
        p=mod.prepare('delete',{'mac':self.rows[0]['mac']},self.groups,self.rows)
        r=mod.execute(self.router,p,self.groups,mod.validated_rows(self.router))
        self.assertEqual('verified',r['status']);self.assertEqual(8,r['after_count'])
        self.assertEqual(self.rows[0]['mac']+';',self.router.sent[0]['mac_addr'])
    def test_full(self):
        self.router.rows.append({'mac':'02:00:00:00:00:FE','ip':'192.168.1.250'})
        with self.assertRaises(ValueError):mod.prepare('add',self.payload(),self.groups,mod.validated_rows(self.router))
    def test_collision_mac(self):
        p=self.payload();p['mac']=self.rows[0]['mac']
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_collision_ip(self):
        p=self.payload();p['ip']=self.rows[0]['ip']
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_gateway_block(self):
        p=self.payload();p['ip']='192.168.1.1'
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_other_network_block(self):
        p=self.payload();p['ip']='192.168.2.100'
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_multicast_rejected(self):
        p=self.payload();p['mac']='01:00:5E:00:00:01'
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_invalid_name(self):
        p=self.payload();p['hostname']='evil\nsubmit'
        with self.assertRaises(ValueError):mod.prepare('add',p,self.groups,self.rows)
    def test_changed_rows_refused(self):
        p=mod.prepare('delete',{'mac':self.rows[0]['mac']},self.groups,self.rows)
        self.router.rows[1]['ip']='192.168.1.99'
        with self.assertRaises(ValueError):mod.execute(self.router,p,self.groups,mod.validated_rows(self.router))
        self.assertEqual([],self.router.sent)
    def test_firmware_mismatch(self):
        g=self.router.query_groups()[0];g['device']['cr_version']='unknown'
        with self.assertRaises(ValueError):mod.prepare('add',self.payload(),g,self.rows)
    def test_empty_router_unexpected(self):
        self.router.rows=[{'mac':'bad','ip':'192.168.1.9'}]
        with self.assertRaises(ValueError):mod.validated_rows(self.router)

if __name__ == '__main__':unittest.main()

class ClientCollisionTests(unittest.TestCase):
    def test_known_other_mac_using_ip_blocked(self):
        class Router:
            def clients(self):return ([{'ip_addr':'192.168.1.50','mac_addr':'02:11:22:33:44:55'}],{})
            def lan_clients(self):return []
        with self.assertRaises(ValueError):
            mod.reject_active_ip_collision(Router(),'02:AA:BB:CC:DD:EE','192.168.1.50')
    def test_matching_mac_accepted(self):
        class Router:
            def clients(self):return ([{'ip_addr':'192.168.1.50','mac_addr':'02:11:22:33:44:55'}],{})
            def lan_clients(self):return []
        mod.reject_active_ip_collision(Router(),'02:11:22:33:44:55','192.168.1.50')