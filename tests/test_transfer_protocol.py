"""Authenticated envelope contract; no sockets or external services."""

import json
import time
import unittest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.transfer_protocol import (EncryptedCodec, MAGIC, MAX_PACKET_BYTES,
                                    Peer, ProtocolError, new_message_id,
                                    new_pairing_key, packet_key_id)


class TransferProtocolTests(unittest.TestCase):
    def setUp(self):
        self.key = new_pairing_key()
        self.codec = EncryptedCodec(self.key)
        self.payload = dict(v=1, kind='text', id=new_message_id(), ts=1000, text='你好 👋')

    def _seal_unvalidated(self, payload):
        header = MAGIC + self.codec.key_id
        nonce = b'\x00' * 12  # Fixed only for crafting one-off invalid test packets.
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return header + nonce + AESGCM(bytes.fromhex(self.key)).encrypt(nonce, data, header)

    def test_round_trip_is_encrypted_and_uses_a_fresh_nonce(self):
        first = self.codec.encode(self.payload, now=1000)
        second = self.codec.encode(self.payload, now=1000)
        self.assertNotEqual(first, second)
        self.assertNotIn(self.payload['text'].encode(), first)
        self.assertEqual(self.codec.decode(first, now=1000), self.payload)
        self.assertEqual(packet_key_id(first), self.codec.key_id)

    def test_ack_round_trip_requires_no_text_field(self):
        ack = {key: value for key, value in self.payload.items() if key != 'text'}
        ack['kind'] = 'ack'
        self.assertEqual(self.codec.decode(self.codec.encode(ack, now=1000), now=1000), ack)
        with self.assertRaises(ProtocolError):
            self.codec.encode(dict(ack, text='unexpected'), now=1000)

    def test_wrong_key_header_nonce_and_ciphertext_are_rejected(self):
        packet = self.codec.encode(self.payload, now=1000)
        with self.assertRaises(ProtocolError):
            EncryptedCodec(new_pairing_key()).decode(packet, now=1000)
        for index in (0, 10, 20, len(packet) - 1):
            tampered = bytearray(packet)
            tampered[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                self.codec.decode(bytes(tampered), now=1000)

    def test_expiry_and_future_clock_skew_are_checked_after_authentication(self):
        packet = self.codec.encode(self.payload, now=1000)
        self.assertEqual(self.codec.decode(packet, now=1060), self.payload)
        for now in (1061, 994):
            with self.subTest(now=now), self.assertRaises(ProtocolError):
                self.codec.decode(packet, now=now)

    def test_strict_authenticated_payload_validation(self):
        invalid = [dict(self.payload, v=True), dict(self.payload, ts=True),
                   dict(self.payload, text=4), dict(self.payload, text=''),
                   dict(self.payload, id='not-a-uuid'), dict(self.payload, kind='forward'),
                   dict(self.payload, extra='no'), dict(self.payload, text='x' * 4097),
                   dict(self.payload, text='中' * 1366), [],
                   b'{"v":1,"v":1}', b'{"ts":' + b'9' * 4500 + b'}']
        for payload in invalid:
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(ProtocolError):
                self.codec.decode(self._seal_unvalidated(payload), now=1000)

    def test_packet_and_text_limits(self):
        payload = dict(self.payload, text='x' * 4096)
        self.assertEqual(self.codec.decode(self.codec.encode(payload, now=1000), now=1000), payload)
        for data in (b'', b'DCC1', b'x' * (MAX_PACKET_BYTES + 1), bytearray(b'x' * 100)):
            with self.assertRaises(ProtocolError):
                self.codec.decode(data, now=1000)
        with self.assertRaises(ProtocolError):
            self.codec.encode(dict(self.payload, text='\ud800'), now=1000)

    def test_pairing_key_and_peer_validation_do_not_expose_key_in_repr(self):
        peer = Peer('Laptop', '127.0.0.1', 45873, self.key)
        self.assertNotIn(self.key, repr(peer))
        self.assertNotEqual(new_pairing_key(), new_pairing_key())
        for key in ('1234', 'x' * 64, ' ' + self.key, bytes.fromhex(self.key)):
            with self.assertRaises(ValueError):
                EncryptedCodec(key)
        for host in ('localhost', 'example.com', '0.0.0.0', '239.1.2.3', '255.255.255.255'):
            with self.assertRaises(ValueError):
                Peer('Laptop', host, 45873, self.key)
        for port in (0, 65536, True, '45873'):
            with self.assertRaises(ValueError):
                Peer('Laptop', '127.0.0.1', port, self.key)


if __name__ == '__main__':
    unittest.main()
