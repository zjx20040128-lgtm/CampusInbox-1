import json
import tempfile
import unittest
from pathlib import Path
from courseinbox.discovery import load_identity, make_proof

TOKEN='test-token-which-is-long-and-not-a-real-secret'
IDENTITY={'device_id':'0123456789abcdef0123456789abcdef','name':'CourseInbox-01234567'}
CHALLENGE='a'*64
PROOF='5f411416cb9ad795ba1992d132238b551d92787f056b7184e1d84c7c80c3f25e'

class IdentityTests(unittest.TestCase):
    def test_identity_survives_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=load_identity(Path(tmp))
            self.assertEqual(first,load_identity(Path(tmp)))
            self.assertRegex(first['device_id'],r'^[a-f0-9]{32}$')
            self.assertEqual(json.loads((Path(tmp)/'mobile-device.json').read_text()),first)
    def test_corrupt_identity_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'mobile-device.json';p.write_text('{"device_id":"bad"}')
            with self.assertRaises(ValueError):load_identity(Path(tmp))
            self.assertEqual(p.read_text(),'{"device_id":"bad"}')
    def test_proof_matches_independent_golden_vector(self):
        result=make_proof(IDENTITY,TOKEN,CHALLENGE,'10.1.2.3',8765)
        self.assertEqual(result,dict(version=1,**IDENTITY,challenge=CHALLENGE,address='10.1.2.3',port=8765,proof=PROOF))
        self.assertNotIn(TOKEN,json.dumps(result))
    def test_invalid_challenge_and_address_are_rejected(self):
        for challenge,address,port in [('A'*64,'10.1.2.3',8765),('a'*63,'10.1.2.3',8765),(CHALLENGE,'evil\naddress',8765),(CHALLENGE,'10.1.2.3',0)]:
            with self.assertRaises(ValueError):make_proof(IDENTITY,TOKEN,challenge,address,port)
