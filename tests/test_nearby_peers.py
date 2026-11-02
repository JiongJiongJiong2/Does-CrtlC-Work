"""Pure Python discovery tests; no radios, Qt app, clipboard or mouse access."""

from dataclasses import FrozenInstanceError
import unittest
from uuid import UUID

from core.nearby_peers import (SERVICE_UUID, NearbyRegistry, decode_advertisement,
                               encode_advertisement, process_instance_id)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class NearbyPeerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.registry = NearbyRegistry(b'own-id', clock=self.clock)
        self.peer_id = b'peer01'
        self.data = encode_advertisement(self.peer_id)

    def test_advertisement_is_23_bytes_with_little_endian_uuid_and_version(self):
        self.assertEqual(len(self.data), 23)
        self.assertEqual(self.data[:16], bytes.fromhex('00485fb5666e1c907d4e114d10cad0b7'))
        self.assertEqual(self.data[:16], UUID(SERVICE_UUID).bytes[::-1])
        self.assertEqual(self.data[16], 1)
        self.assertEqual(decode_advertisement(self.data), self.peer_id)
        # 23 payload + 2 AD header + 3 flags fits a legacy 31-byte advertisement.
        self.assertLessEqual(len(self.data) + 2 + 3, 31)

    def test_guid_memory_layout_is_not_accepted_as_ble_wire_order(self):
        guid_layout = UUID(SERVICE_UUID).bytes_le + b'\x01' + self.peer_id
        with self.assertRaises(ValueError):
            decode_advertisement(guid_layout)

    def test_identity_size_uuid_version_and_payload_size_are_validated(self):
        for invalid in (b'', b'short', b'too-long', 'peer01', 123):
            with self.assertRaises(ValueError):
                encode_advertisement(invalid)
        for invalid in (b'', self.data[:-1], self.data + b'x',
                        b'x' + self.data[1:], self.data[:16] + b'\x02' + self.data[17:]):
            with self.assertRaises(ValueError):
                decode_advertisement(invalid)
            self.assertIsNone(self.registry.observe(invalid, 'address', -55))

    def test_process_identity_is_stable_and_own_advertisement_is_ignored(self):
        first, second = NearbyRegistry(), NearbyRegistry()
        self.assertEqual(first.instance_id, process_instance_id())
        self.assertEqual(first.instance_id, second.instance_id)
        self.assertEqual(len(first.instance_id), 6)
        self.assertIsNone(first.observe(encode_advertisement(first.instance_id), 'self', -20))
        self.assertEqual(first.peers(), ())

    def test_same_identity_updates_address_name_and_last_seen_without_duplicate(self):
        self.registry.observe(self.data, 'AA:BB', -50, ' Desk\nComputer ')
        self.clock.value = 2
        peer = self.registry.observe(self.data, 'CC:DD', -60)
        self.assertEqual(len(self.registry.peers()), 1)
        self.assertEqual(peer.bluetooth_address, 'CC:DD')
        self.assertEqual(peer.name, 'Desk Computer')
        self.assertEqual(peer.last_seen, 2)
        self.assertEqual(peer.rssi, -55)
        with self.assertRaises(FrozenInstanceError):
            peer.name = 'mutated'

    def test_identity_entry_validates_bytes_and_matches_self_and_address_rules(self):
        for invalid in (b'', b'short', b'too-long', 'peer01', 123, bytearray(b'peer01')):
            self.assertIsNone(self.registry.observe_identity(invalid, 'address', -55))
        self.assertIsNone(self.registry.observe_identity(b'own-id', 'self', -20))
        self.assertEqual(self.registry.peers(), ())
        for observe, identifier in ((self.registry.observe, self.data),
                                    (self.registry.observe_identity, self.peer_id)):
            for address in ('', ' ', 'x' * 129, None):
                with self.assertRaises(ValueError):
                    observe(identifier, address, -55)

    def test_identity_and_packet_entries_share_ttl_updates_and_out_of_range_rules(self):
        direct = NearbyRegistry(b'own-id', clock=self.clock)
        paths = ((self.registry.observe, self.data), (direct.observe_identity, self.peer_id))
        for observe, identifier in paths:
            self.assertIsNone(observe(identifier, 'stale', -127))
        self.assertEqual(self.registry.peers(), direct.peers())
        self.assertEqual(self.registry.peers(), ())

        for now, address, rssi, name in ((0, 'first', -60, ' First '),
                                         (2, 'current', -65, 'Current')):
            self.clock.value = now
            observations = [observe(identifier, address, rssi, name)
                            for observe, identifier in paths]
            self.assertEqual(observations[0], observations[1])
        self.clock.value = 13
        for observe, identifier in paths:
            self.assertIsNone(observe(identifier, 'out-of-range', -127.0, 'Stale'))
        self.assertEqual(self.registry.peers(), direct.peers())
        self.assertEqual(direct.candidate.last_seen, 2)
        self.assertEqual(direct.candidate.bluetooth_address, 'current')
        self.clock.value = 14
        self.assertEqual(self.registry.expire(), direct.expire())
        self.assertIsNone(self.registry.candidate)
        self.assertIsNone(direct.candidate)

    def test_expiry_uses_last_observation_and_removes_candidate(self):
        self.registry.observe(self.data, 'address', -60)
        self.clock.value = 11
        self.assertIsNotNone(self.registry.candidate)
        self.registry.observe(self.data, 'address', -65)
        self.clock.value = 22
        self.assertEqual(self.registry.expire(), [])
        self.clock.value = 23
        self.assertEqual([peer.id for peer in self.registry.expire()], [self.peer_id])
        self.assertIsNone(self.registry.candidate)

    def test_out_of_range_old_advertisement_cannot_create_a_peer(self):
        for rssi in (-127, -127.0):
            self.assertIsNone(self.registry.observe(self.data, 'old-address', rssi))
        self.assertEqual(self.registry.peers(), ())
        self.assertIsNone(self.registry.candidate)

    def test_out_of_range_old_advertisement_cannot_refresh_or_change_existing_peer(self):
        self.registry.observe(self.data, 'original-address', -60, 'Original')
        self.clock.value = 11
        self.assertIsNone(self.registry.observe(self.data, 'stale-address', -127, 'Stale'))
        peer = self.registry.candidate
        self.assertEqual(peer.last_seen, 0)
        self.assertEqual(peer.bluetooth_address, 'original-address')
        self.assertEqual(peer.name, 'Original')
        self.clock.value = 12
        self.assertEqual([peer.id for peer in self.registry.expire()], [self.peer_id])
        self.assertIsNone(self.registry.candidate)

    def test_rssi_requires_samples_and_median_does_not_imply_a_direction(self):
        first = self.registry.observe(self.data, 'address', -57)
        self.assertEqual(first.proximity, 'unknown')
        self.registry.observe(self.data, 'address', -58)
        peer = self.registry.observe(self.data, 'address', -110)
        self.assertEqual(peer.rssi, -58)
        self.assertEqual(peer.proximity, 'near')
        self.assertFalse(hasattr(peer, 'direction'))
        self.assertFalse(hasattr(peer, 'trusted'))
        self.registry.clear()
        for value in (-85, -82, -90):
            peer = self.registry.observe(self.data, 'address', value)
        self.assertEqual(peer.proximity, 'far')

    def test_old_rssi_samples_expire_even_if_peer_keeps_advertising(self):
        for _ in range(3):
            self.registry.observe(self.data, 'address', -50)
        self.clock.value = 6
        peer = self.registry.observe(self.data, 'address', 127)
        self.assertEqual(peer.proximity, 'unknown')
        self.assertEqual(peer.sample_count, 0)
        self.assertIsNone(peer.rssi)
        self.assertIsNotNone(self.registry.candidate)

    def test_no_preferred_candidate_with_multiple_peers_despite_signal_difference(self):
        for _ in range(3):
            self.registry.observe(self.data, 'nearby', -35)
            self.registry.observe(encode_advertisement(b'peer02'), 'further', -100)
        self.assertEqual(len(self.registry.peers()), 2)
        self.assertIsNone(self.registry.candidate)

    def test_rssi_and_peer_capacity_are_bounded_without_strength_based_eviction(self):
        registry = NearbyRegistry(b'own-id', clock=self.clock, max_samples=3, max_peers=2)
        for value in (-50, -60, -70, -80):
            peer = registry.observe(self.data, 'first', value)
        self.assertEqual(peer.sample_count, 3)
        self.assertEqual(peer.rssi, -70)
        self.clock.value = 1
        registry.observe(encode_advertisement(b'peer02'), 'second', -100)
        self.clock.value = 2
        registry.observe(encode_advertisement(b'peer03'), 'third', -30)
        self.assertEqual([peer.id for peer in registry.peers()], [b'peer02', b'peer03'])

    def test_invalid_rssi_does_not_become_near_or_create_a_fake_sample(self):
        for invalid in (127, float('nan'), float('inf'), -150, 'strong', True):
            peer = self.registry.observe(self.data, 'address', invalid)
        self.assertEqual(peer.sample_count, 0)
        self.assertEqual(peer.proximity, 'unknown')


if __name__ == '__main__':
    unittest.main()
