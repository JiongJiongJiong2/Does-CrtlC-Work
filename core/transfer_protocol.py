"""Transport-neutral, authenticated short-text envelopes for paired devices."""

import hashlib
from dataclasses import dataclass, field
import ipaddress
import json
import re
import secrets
import time
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_PACKET_BYTES = 8192
MAX_TEXT_BYTES = 4096
TTL_SECONDS = 60
FUTURE_SKEW_SECONDS = 5
MAGIC = b'DCC1'
HEADER_BYTES = 20
NONCE_BYTES = 12


class ProtocolError(ValueError):
    """An untrusted packet or local input does not meet the protocol contract."""


def new_pairing_key():
    return secrets.token_hex(32)


def new_message_id():
    return str(uuid.uuid4())


def pairing_key_bytes(key):
    if type(key) is not str or re.fullmatch(r'[0-9a-fA-F]{64}', key) is None:
        raise ProtocolError('Pairing key must contain exactly 64 hexadecimal characters')
    return bytes.fromhex(key)


def peer_address(host, *, bind=False):
    if type(host) is not str:
        raise ValueError('Address must be an IP literal')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError('Address must be an IP literal') from None
    if address.is_multicast or (not bind and address.is_unspecified) or (
            address.version == 4 and int(address) & 255 == 255):
        raise ValueError('Broadcast, multicast and unspecified destinations are unsupported')
    return address


@dataclass(frozen=True)
class Peer:
    name: str
    host: str
    port: int
    key: str = field(repr=False)

    def __post_init__(self):
        if type(self.name) is not str or not self.name.strip() or len(self.name.encode('utf-8')) > 80:
            raise ValueError('Peer name must contain 1 to 80 UTF-8 bytes')
        peer_address(self.host)
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Peer port must be between 1 and 65535')
        pairing_key_bytes(self.key)


def packet_key_id(packet):
    if (type(packet) is not bytes or not HEADER_BYTES + NONCE_BYTES + 16 < len(packet)
            <= MAX_PACKET_BYTES or packet[:4] != MAGIC):
        raise ProtocolError('Invalid packet envelope')
    return packet[4:HEADER_BYTES]


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError('Duplicate payload field')
        result[key] = value
    return result


def validate_payload(payload, *, now=None):
    """Return validated data; booleans, extra fields and expired packets fail."""
    now = time.time() if now is None else now
    if type(payload) is not dict or type(payload.get('kind')) is not str:
        raise ProtocolError('Invalid message payload')
    kind = payload['kind']
    fields = {'v', 'kind', 'id', 'ts', 'text'} if kind == 'text' else {'v', 'kind', 'id', 'ts'}
    if kind not in ('text', 'ack') or set(payload) != fields:
        raise ProtocolError('Unsupported message fields')
    if type(payload['v']) is not int or payload['v'] != 1:
        raise ProtocolError('Unsupported protocol version')
    message_id = payload['id']
    if type(message_id) is not str:
        raise ProtocolError('Invalid message identifier')
    try:
        parsed = uuid.UUID(message_id)
    except (ValueError, AttributeError):
        raise ProtocolError('Invalid message identifier') from None
    if str(parsed) != message_id or parsed.version != 4:
        raise ProtocolError('Invalid message identifier')
    timestamp = payload['ts']
    if (type(timestamp) is not int or timestamp < now - TTL_SECONDS or
            timestamp > now + FUTURE_SKEW_SECONDS):
        raise ProtocolError('Message timestamp is outside the allowed window')
    if kind == 'text':
        if type(payload['text']) is not str:
            raise ProtocolError('Text must be a string')
        try:
            length = len(payload['text'].encode('utf-8'))
        except UnicodeError:
            raise ProtocolError('Text is not valid UTF-8') from None
        if not 0 < length <= MAX_TEXT_BYTES:
            raise ProtocolError('Text must contain 1 to 4096 UTF-8 bytes')
    return payload


class EncryptedCodec:
    """AES-256-GCM; key routing header is authenticated as associated data.

    text: {v: 1, kind: 'text', id: UUID4, ts: epoch seconds, text: str}
    ack:  {v: 1, kind: 'ack',  id: original UUID4, ts: epoch seconds}
    Replay suppression belongs to each receiving transport/session.
    """

    def __init__(self, key):
        raw_key = pairing_key_bytes(key)
        self.key_id = hashlib.sha256(raw_key).digest()[:16]
        self._cipher = AESGCM(raw_key)

    def encode(self, payload, *, now=None):
        validate_payload(payload, now=now)
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        nonce = secrets.token_bytes(NONCE_BYTES)
        header = MAGIC + self.key_id
        packet = header + nonce + self._cipher.encrypt(nonce, plaintext, header)
        if len(packet) > MAX_PACKET_BYTES:
            raise ProtocolError('Encrypted packet is too large')
        return packet

    def decode(self, packet, *, now=None):
        if packet_key_id(packet) != self.key_id:
            raise ProtocolError('Unknown pairing key')
        header = packet[:HEADER_BYTES]
        nonce = packet[HEADER_BYTES:HEADER_BYTES + NONCE_BYTES]
        try:
            plaintext = self._cipher.decrypt(nonce, packet[HEADER_BYTES + NONCE_BYTES:], header)
            payload = json.loads(plaintext, object_pairs_hook=_strict_object)
            return validate_payload(payload, now=now)
        except (InvalidTag, UnicodeError, ValueError, RecursionError):
            raise ProtocolError('Packet authentication or payload validation failed') from None
