import unittest
import requests
from tests.helpers import NetworkTest
import os
import time
import json

CONTROLLER = '127.0.0.1'
KYTOS_API = 'http://%s:8181/api/kytos' % (CONTROLLER)


class TestE2EMefEline(unittest.TestCase):
    net = None
    @classmethod
    def setUpClass(cls):
        cls.net = NetworkTest(CONTROLLER)
        cls.net.start()
        cls.net.restart_kytos_clean()

    @classmethod
    def tearDownClass(cls):
        cls.net.stop()

    def test_001_list_evcs_should_be_empty(self):
        """Test if list circuits return 'no circuit stored.'."""
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.get(api_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})

    def test_010_create_evc_intra_switch(self):
        """ create an intra-switch EVC e-line with VLAN tag 
        (UNIs in the same switch) """
        payload = {
            "name": "my evc1",
            "enabled": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": {
                    "tag_type": 1,
                    "value": 101
                }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:01:4",
                "tag": {
                    "tag_type": 1,
                    "value": 101
                }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, json=json.dumps(payload))
        self.assertEqual(response.status_code, 201)

        h1, h2 = self.net.get( 'h1', 'h2' )
        result = h1.cmd( 'ping -c1', h2.IP() )
        self.assertIn(', 0% packet loss,', result)
        data = response.json()
        self.assertIn('circuit_id', data)

        s1 = self.net.get( 's1' )
        flows_s1 = s1.dpctl('dump-flows')
        # Each switch must have 3 flows: 01 for LLDP + 02 for the EVC (ingress + egress)
        self.assertEqual(len(flows_s1.split('\r\n ')), 3)

        # TODO: make sure it should be dl_vlan instead of vlan_vid
        self.assertIn('dl_vlan=100', flows_s1)

    def test_015_create_evc_inter_switch(self):
        payload = {
            "name": "my evc1",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": {
                    "tag_type": 1,
                    "value": 15
                }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": {
                    "tag_type": 1,
                    "value": 15
                }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        time.sleep(5)

        # Each switch must have 3 flows: 01 for LLDP + 02 for the EVC (ingress + egress)
        s1, s2 = self.net.net.get( 's1', 's2' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 3
        assert len(flows_s2.split('\r\n ')) == 3

        # make sure it should be dl_vlan instead of vlan_vid
        assert 'dl_vlan=15' in flows_s1
        assert 'dl_vlan=15' in flows_s2

        # Make the final and most important test: connectivity
        # 1. create the vlans and setup the ip addresses
        # 2. try to ping each other
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan15 type vlan id 15' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan15')
        h11.cmd('ip addr add 15.0.0.11/24 dev vlan15')
        h2.cmd('ip link add link %s name vlan15 type vlan id 15' % (h2.intfNames()[0]))
        h2.cmd('ip link set up vlan15')
        h2.cmd('ip addr add 15.0.0.2/24 dev vlan15')
        result = h11.cmd( 'ping -c1 15.0.0.2' )
        assert ', 0% packet loss,' in result

        # clean up
        h11.cmd('ip link del vlan15')
        h2.cmd('ip link del vlan15')
        self.net.restart_kytos_clean()

    def test_020_create_evc_different_tags_each_side(self):
        payload = {
            "name": "Vlan102_103_Test",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 102 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": { "tag_type": 1, "value": 103 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        time.sleep(5)

        # Each switch must have 3 flows: 01 for LLDP + 02 for the EVC (ingress + egress)
        s1, s2 = self.net.net.get( 's1', 's2' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 3
        assert len(flows_s2.split('\r\n ')) == 3

        # make sure it should be dl_vlan instead of vlan_vid
        assert 'dl_vlan=102' in flows_s1
        assert 'dl_vlan=103' in flows_s2

        # Make the final and most important test: connectivity
        # 1. create the vlans and setup the ip addresses
        # 2. try to ping each other
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan102 type vlan id 102' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan102')
        h11.cmd('ip addr add 102.103.0.11/24 dev vlan102')
        h2.cmd('ip link add link %s name vlan103 type vlan id 103' % (h2.intfNames()[0]))
        h2.cmd('ip link set up vlan103')
        h2.cmd('ip addr add 102.103.0.2/24 dev vlan103')
        result = h11.cmd( 'ping -c1 102.103.0.2' )
        assert ', 0% packet loss,' in result

        # clean up
        h11.cmd('ip link del vlan102')
        h2.cmd('ip link del vlan103')
        self.net.restart_kytos_clean()

    def test_020_create_evc_tag_notag(self):
        payload = {
            "name": "Vlan104_Test",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 104 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1"
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        time.sleep(5)

        # Each switch must have 3 flows: 01 for LLDP + 02 for the EVC (ingress + egress)
        s1, s2 = self.net.net.get( 's1', 's2' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 3
        assert len(flows_s2.split('\r\n ')) == 3

        # make sure it should be dl_vlan instead of vlan_vid
        assert 'dl_vlan=104' in flows_s1
        assert 'dl_vlan=104' not in flows_s2

        # Make the final and most important test: connectivity
        # 1. create the vlans and setup the ip addresses
        # 2. try to ping each other
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan104 type vlan id 104' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan104')
        h11.cmd('ip addr add 104.0.0.11/24 dev vlan104')
        h2.cmd('ip addr add 104.0.0.2/24 dev %s' % (h2.intfNames()[0]))
        result = h11.cmd( 'ping -c1 104.0.0.2' )

        # make sure it should be dl_vlan instead of vlan_vid
        assert 'dl_vlan=104' in flows_s1

        # clean up
        h11.cmd('ip link del vlan104')
        h2.cmd('ip addr del 104.0.0.2/24 dev %s' % (h2.intfNames()[0]))
        self.net.restart_kytos_clean()

    def test_020_create_evc_same_vid_different_uni(self):
        # Create circuit 1
        payload = {
            "name": "Vlan110_Test",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 110 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": { "tag_type": 1, "value": 110 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        evc1 = data['circuit_id']
        time.sleep(5)

        # Create circuit 2: same vlan id but in different UNIs
        payload = {
            "name": "Vlan110_Test2",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:2",
                "tag": { "tag_type": 1, "value": 110 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:03:1",
                "tag": { "tag_type": 1, "value": 110 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        evc2 = data['circuit_id']
        assert evc1 != evc2
        time.sleep(5)

        # The switch 1 should have 5 flows: 01 for LLDP + 02 for evc1 + 02 for evc2
        # The switches 2 and 3 should have 3 flows: 01 for LLDP + 02 for each evc
        s1, s2, s3 = self.net.net.get( 's1', 's2', 's3' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        flows_s3 = s3.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 5
        assert len(flows_s2.split('\r\n ')) == 3
        assert len(flows_s3.split('\r\n ')) == 3

        # make sure it should be dl_vlan instead of vlan_vid
        assert 'dl_vlan=110' in flows_s1
        assert 'dl_vlan=110' in flows_s2
        assert 'dl_vlan=110' in flows_s3

        # Make the final and most important test: connectivity
        # 1. create the vlans and setup the ip addresses
        # 2. try to ping each other
        # for evc 1:
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan110 type vlan id 110' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan110')
        h11.cmd('ip addr add 110.0.0.11/24 dev vlan110')
        h2.cmd('ip link add link %s name vlan110 type vlan id 110' % (h2.intfNames()[0]))
        h2.cmd('ip link set up vlan110')
        h2.cmd('ip addr add 110.0.0.2/24 dev vlan110')
        result = h11.cmd( 'ping -c1 110.0.0.2' )
        assert ', 0% packet loss,' in result

        # for evc 2:
        h12, h3 = self.net.net.get( 'h12', 'h3' )
        h12.cmd('ip link add link %s name vlan110 type vlan id 110' % (h12.intfNames()[0]))
        h12.cmd('ip link set up vlan110')
        h12.cmd('ip addr add 110.0.0.12/24 dev vlan110')
        h3.cmd('ip link add link %s name vlan110 type vlan id 110' % (h3.intfNames()[0]))
        h3.cmd('ip link set up vlan110')
        h3.cmd('ip addr add 110.0.0.3/24 dev vlan110')
        result = h12.cmd( 'ping -c1 110.0.0.3' )
        assert ', 0% packet loss,' in result

        # clean up
        h11.cmd('ip link del vlan110')
        h12.cmd('ip link del vlan110')
        h2.cmd('ip link del vlan110')
        h3.cmd('ip link del vlan110')
        self.net.restart_kytos_clean()

    def test_025_disable_circuit_should_remove_openflow_rules(self):
        # let's suppose that xyz is the circuit id previously created
        # curl -X PATCH -H "Content-Type: application/json" -d '{"enable": false}' http://172.18.0.2:8181/api/kytos/mef_eline/v2/evc/xyz
        payload = {
            "name": "Vlan125_Test_evc1",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 125 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": { "tag_type": 1, "value": 125 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        evc1 = data['circuit_id']
        time.sleep(5)

        # disable the circuit
        payload = {"enable": False}
        api_url += evc1
        response = requests.patch(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 200

        # Each switch should have only one flow: LLDP
        s1, s2 = self.net.net.get( 's1', 's2' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 1
        assert len(flows_s2.split('\r\n ')) == 1

        # Nodes should not be able to ping each other
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan125 type vlan id 125' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan125')
        h11.cmd('ip addr add 125.0.0.11/24 dev vlan125')
        h2.cmd('ip link add link %s name vlan125 type vlan id 125' % (h2.intfNames()[0]))
        h2.cmd('ip link set up vlan125')
        h2.cmd('ip addr add 125.0.0.2/24 dev vlan125')
        result = h11.cmd( 'ping -c1 125.0.0.2' )
        assert ', 100% packet loss,' in result

        # clean up
        h11.cmd('ip link del vlan125')
        h2.cmd('ip link del vlan125')
        self.net.restart_kytos_clean()

    def test_025_create_circuit_reusing_same_vlanid_from_previous_evc(self):
        payload = {
            "name": "Vlan125_Test_evc1",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 125 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": { "tag_type": 1, "value": 125 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        evc1 = data['circuit_id']
        time.sleep(10)

        # disable the circuit
        payload = {"enable": False}
        api_url += evc1
        response = requests.patch(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 200
        time.sleep(10)

        # try to reuse the vlan id
        payload = {
            "name": "Vlan125_Test_evc2",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "00:00:00:00:00:00:00:01:1",
                "tag": { "tag_type": 1, "value": 125 }
            },
            "uni_z": {
                "interface_id": "00:00:00:00:00:00:00:02:1",
                "tag": { "tag_type": 1, "value": 125 }
            }
        }
        api_url = KYTOS_API+'/mef_eline/v2/evc/'
        response = requests.post(api_url, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201
        data = response.json()
        assert 'circuit_id' in data
        evc2 = data['circuit_id']
        assert evc1 != evc2
        time.sleep(10)

        # The switches should have 3 flows: 01 for LLDP + 02 for each evc
        s1, s2 = self.net.net.get( 's1', 's2' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        print flows_s1
        print flows_s2
        assert len(flows_s1.split('\r\n ')) == 3
        assert len(flows_s2.split('\r\n ')) == 3

        # Nodes should be able to ping each other
        h11, h2 = self.net.net.get( 'h11', 'h2' )
        h11.cmd('ip link add link %s name vlan125 type vlan id 125' % (h11.intfNames()[0]))
        h11.cmd('ip link set up vlan125')
        h11.cmd('ip addr add 125.0.0.11/24 dev vlan125')
        h2.cmd('ip link add link %s name vlan125 type vlan id 125' % (h2.intfNames()[0]))
        h2.cmd('ip link set up vlan125')
        h2.cmd('ip addr add 125.0.0.2/24 dev vlan125')
        result = h11.cmd( 'ping -c1 125.0.0.2' )
        assert ', 0% packet loss,' in result

        # clean up
        h11.cmd('ip link del vlan125')
        h2.cmd('ip link del vlan125')
        self.net.restart_kytos_clean()

    def test_030_patch_evc_new_name(self):
        # TODO
        assert True

    def test_040_patch_evc_new_unis(self):
        # TODO
        assert True

    def test_050_disable_evc(self):
        # TODO
        assert True

    def test_060_on_primary_path_fail_should_migrate_to_backup(self):
        # TODO
        assert True

    def test_on_primary_path_fail_should_migrate_to_backup(self):
        # TODO: When the primary_path is down and backup_path exists and is UP
        # the circuit will change from primary_path to backup_path.

        payload = {
         "name": "my evc1",
         "enabled": True,
         "uni_a": {
             "interface_id": "00:00:00:00:00:00:00:01:1",
             "tag": {
                 "tag_type": 1,
                 "value": 101
             }
         },
         "uni_z": {
             "interface_id": "00:00:00:00:00:00:00:01:4",
             "tag": {
                 "tag_type": 1,
                 "value": 101
             }
         },
          "current_path": [],
         "primary_path": [
             {"endpoint_a": {"interface_id": "00:00:00:00:00:00:00:01:1"},
              "endpoint_b": {"interface_id": "00:00:00:00:00:00:00:03:1"}}
         ],
         "backup_path": [
             {"endpoint_a": {"interface_id": "00:00:00:00:00:00:00:01:1"},
              "endpoint_b": {"interface_id": "00:00:00:00:00:00:00:04:1"}}
         ]
        }
    
    
        """disabling links to test if back-up path is taken"""
        net.configLinkStatus('s1','s3','down') # used to up/down the link.
    
        """Check on the virtual switches directly for flows"""
        # Each switch must have 3 flows: 01 for LLDP + 02 for the EVC (ingress + egress)
        s1, s2, s3, s4 = self.net.net.get( 's1', 's2', 's3','s4' )
        flows_s1 = s1.dpctl('dump-flows')
        flows_s2 = s2.dpctl('dump-flows')
        flows_s3 = s3.dpctl('dump-flows')
        flows_s4 = s4.dpctl('dump-flows')
        assert len(flows_s1.split('\r\n ')) == 3
        assert len(flows_s2.split('\r\n ')) == 3
        assert len(flows_s3.split('\r\n ')) == 3
        assert len(flows_s4.split('\r\n ')) == 3
    
        """Make api request for @current_path"""
        url = "http://67.17.206.252:8181/api/kytos/mef_eline/v2/evc/"
        request = requests.post(url=url, json=payload)
    
        """Parse incomming json file for @current_path"""
        current_path = json.loads(request.content.decode("utf-8")) #reading from json file
    
        """Compare @current_path with expected backup_path"""
    
        path_taken = current_path
        path_backup = [ {"endpoint_a": {"interface_id": "00:00:00:00:00:00:00:01:1"},
        "endpoint_b": {"interface_id": "00:00:00:00:00:00:00:04:1"}}]
    
        self.assertEqual(path_taken, path_backup)
    
        # self.assertTrue(True)
        
    def test_070_on_primary_path_fail_should_migrate_to_backup_with_dynamic_discovery_enabled(self):
        #TODO
        # payload = {
        #     "name": "my evc1",
        #     "enabled": True,
        #     "uni_a": {
        #         "interface_id": "00:00:00:00:00:00:00:01:1",
        #         "tag": {
        #             "tag_type": 1,
        #             "value": 101
        #         }
        #     },
        #     "uni_z": {
        #         "interface_id": "00:00:00:00:00:00:00:01:4",
        #         "tag": {
        #             "tag_type": 1,
        #             "value": 101
        #         }
        #     },
        #      "current_path": [],
        #     "primary_path": [],
        #     "backup_path": [],
        #     "dynamic_backup_path": "true",
        #         "active": "true",
        #         "enabled": "true"
        # }
        
        self.assertTrue(True)
