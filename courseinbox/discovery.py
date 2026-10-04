"""Stable pairing identity and optional LAN discovery; never publishes credentials."""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

SERVICE_TYPE = '_courseinbox._tcp.local.'
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))


def load_identity(directory: Path) -> dict:
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'mobile-device.json'
    if not path.exists():
        ident=secrets.token_hex(16)
        obj={'device_id':ident,'name':'CourseInbox-'+ident[:8]}
        fd,tmp=tempfile.mkstemp(prefix='mobile-device-',dir=directory)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(obj,stream);stream.flush();os.fsync(stream.fileno())
            try: os.link(tmp,path)
            except FileExistsError: pass
        finally: os.unlink(tmp)
    try:
        result=json.loads(path.read_text(encoding='utf-8-sig'))
        ident=result['device_id']
        if not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{32}',ident) or result.get('name')!='CourseInbox-'+ident[:8]:
            raise ValueError()
        return {'device_id':ident,'name':result['name']}
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError('mobile-device.json invalid; restore the saved identity before restarting') from error


def private_ipv4(address: str) -> bool:
    try:
        ip=ipaddress.ip_address(address)
        return isinstance(ip,ipaddress.IPv4Address) and any(ip in n for n in PRIVATE_NETWORKS)
    except ValueError: return False


def make_proof(identity: dict, token: str, challenge: str, address: str, port: int) -> dict:
    if not re.fullmatch('[0-9a-f]{64}',challenge) or not re.fullmatch('[0-9a-f]{32}',identity['device_id']):
        raise ValueError('Invalid pairing challenge')
    if str(ipaddress.IPv4Address(address))!=address or not 1<=port<=65535:
        raise ValueError('Invalid pairing endpoint')
    message='\n'.join(('courseinbox-pair-v1',identity['device_id'],challenge,address,str(port)))
    proof=hmac.new(token.encode('utf-8'),message.encode('utf-8'),hashlib.sha256).hexdigest()
    return dict(version=1,**identity,challenge=challenge,address=address,port=port,proof=proof)
