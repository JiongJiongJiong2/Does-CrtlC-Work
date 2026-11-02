"""Untrusted BLE discovery identities, independent of pairing and text transport.

A matching advertisement only says that a device speaks this discovery format.
It neither authenticates that device nor authorizes clipboard access, sending,
mouse control or a connection. RSSI hints cannot identify left/right placement.
"""

from collections import deque
from dataclasses import dataclass, field
import math
import secrets
import statistics
import time
from uuid import UUID


SERVICE_UUID = 'b7d0ca10-4d11-4e7d-901c-6e66b55f4800'
ADVERTISEMENT_VERSION = 1
# BLE service-data UUIDs reverse all 16 canonical bytes. UUID.bytes_le is
# Windows GUID's mixed-endian memory layout and is not the BLE wire format.
_UUID_BYTES = UUID(SERVICE_UUID).bytes[::-1]
_PROCESS_INSTANCE_ID = secrets.token_bytes(6)


def process_instance_id():
    """One random identity for this process lifetime, never a persistent device ID."""
    return _PROCESS_INSTANCE_ID


def _validate_instance_id(instance_id):
    if type(instance_id) is not bytes or len(instance_id) != 6:
        raise ValueError('instance_id must be exactly six bytes')


def encode_advertisement(instance_id):
    """Return the complete 23-byte AD 0x21 payload, including its 128-bit UUID.

    The advertising backend adds the AD length/type bytes. A GATT advertising
    API that inserts the service UUID itself must receive only payload[16:].
    """
    _validate_instance_id(instance_id)
    return _UUID_BYTES + bytes((ADVERTISEMENT_VERSION,)) + instance_id


def decode_advertisement(data):
    """Validate the complete service-data payload; return an untrusted identity."""
    if type(data) is not bytes or len(data) != 23:
        raise ValueError('advertisement payload must be exactly 23 bytes')
    if data[:16] != _UUID_BYTES or data[16] != ADVERTISEMENT_VERSION:
        raise ValueError('unsupported discovery service or protocol version')
    return data[17:]


@dataclass(frozen=True)
class NearbyPeer:
    """An observation with a temporary, untrusted discovery identifier."""

    id: bytes
    bluetooth_address: str
    rssi: float | None
    last_seen: float
    name: str | None = None
    sample_count: int = 0
    proximity: str = 'unknown'

    @property
    def instance_id(self):
        """Compatibility alias; this ID need not be a verified process identity."""
        return self.id


@dataclass
class _Observation:
    bluetooth_address: str
    last_seen: float
    name: str | None
    samples: deque = field(default_factory=deque)


class NearbyRegistry:
    """Deduplicate live advertisements without selecting or trusting a device.

    Access from one owning thread; the clock is injectable for deterministic
    expiry. IDs may come from a process advertisement or a temporary Bluetooth
    address observed by a backend; neither is a stable or trusted device ID.
    ``candidate`` is present only when exactly one peer is currently visible,
    even if another peer has a much weaker signal.
    """

    def __init__(self, instance_id=None, *, clock=time.monotonic, ttl=12.0,
                 sample_window=6.0, max_samples=7, min_samples=3, max_peers=64):
        self.instance_id = process_instance_id() if instance_id is None else instance_id
        _validate_instance_id(self.instance_id)
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError('ttl must be positive and finite')
        if not math.isfinite(sample_window) or sample_window <= 0:
            raise ValueError('sample_window must be positive and finite')
        if not 1 <= min_samples <= max_samples or max_peers < 1:
            raise ValueError('invalid discovery capacity or sample limits')
        self._clock = clock
        self._ttl = float(ttl)
        self._sample_window = float(sample_window)
        self._max_samples = int(max_samples)
        self._min_samples = int(min_samples)
        self._max_peers = int(max_peers)
        self._observations = {}

    def observe(self, data, bluetooth_address, rssi=None, name=None):
        """Record one broadcast; malformed packets and our own broadcasts are ignored."""
        try:
            identity = decode_advertisement(data)
        except ValueError:
            return None
        return self.observe_identity(identity, bluetooth_address, rssi, name)

    def observe_identity(self, identity, bluetooth_address, rssi=None, name=None):
        """Record a backend observation without inventing a service-data packet.

        The six-byte ID is only a temporary deduplication key. Accepting it does
        not establish the advertising process's identity or authorize a link.
        """
        try:
            _validate_instance_id(identity)
        except ValueError:
            return None
        if identity == self.instance_id:
            return None
        # Windows uses -127 for an out-of-range event carrying the last seen
        # advertisement. It is not a new observation and must not renew its TTL.
        if type(rssi) in (int, float) and rssi == -127:
            return None
        if (type(bluetooth_address) is not str or not bluetooth_address.strip()
                or len(bluetooth_address) > 128):
            raise ValueError('bluetooth_address must be a nonempty backend address')
        now = self._clock()
        self._expire_at(now)
        observation = self._observations.get(identity)
        if observation is None:
            if len(self._observations) >= self._max_peers:
                oldest = min(self._observations, key=lambda key: self._observations[key].last_seen)
                del self._observations[oldest]
            observation = _Observation(bluetooth_address, now, None,
                                       deque(maxlen=self._max_samples))
            self._observations[identity] = observation
        observation.bluetooth_address = bluetooth_address
        observation.last_seen = now
        if isinstance(name, str) and name.strip():
            observation.name = ' '.join(name.split())[:80]
        self._prune_samples(observation, now)
        # 127 is the usual unavailable-RSSI sentinel. Bad samples do not make
        # a valid peer disappear, and are never treated as an extremely close peer.
        if (type(rssi) in (int, float) and math.isfinite(rssi)
                and -127 < rssi <= 20):
            observation.samples.append((now, float(rssi)))
        return self._snapshot(identity, observation, now)

    def _prune_samples(self, observation, now):
        while observation.samples and now - observation.samples[0][0] >= self._sample_window:
            observation.samples.popleft()

    def _snapshot(self, identity, observation, now):
        self._prune_samples(observation, now)
        samples = [value for _, value in observation.samples]
        median = statistics.median(samples) if samples else None
        proximity = 'unknown'
        if len(samples) >= self._min_samples:
            if median >= -65:
                proximity = 'near'
            elif median <= -80:
                proximity = 'far'
        return NearbyPeer(identity, observation.bluetooth_address, median,
                          observation.last_seen, observation.name, len(samples), proximity)

    def _expire_at(self, now):
        expired = []
        for identity, observation in tuple(self._observations.items()):
            if now - observation.last_seen >= self._ttl:
                expired.append(self._snapshot(identity, observation, now))
                del self._observations[identity]
        return expired

    def expire(self):
        return self._expire_at(self._clock())

    def peers(self):
        now = self._clock()
        self._expire_at(now)
        # Identity order is stable and does not imply RSSI-based preference.
        return tuple(self._snapshot(identity, self._observations[identity], now)
                     for identity in sorted(self._observations))

    @property
    def candidate(self):
        peers = self.peers()
        return peers[0] if len(peers) == 1 else None

    def clear(self):
        self._observations.clear()
