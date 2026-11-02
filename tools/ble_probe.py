"""Explicit BLE diagnostics; never runs as part of normal app startup.

python tools/ble_probe.py --scan
python tools/ble_probe.py --device SCAN_ID --send "hello"
The second command prompts for the shared key; a matching peripheral is required.
"""

import argparse
from getpass import getpass
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description='Experimental DoseCtrlC BLE central; RSSI is not direction')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--scan', action='store_true')
    mode.add_argument('--device', help='opaque ID printed by --scan')
    parser.add_argument('--send', help='explicit test text (up to 4096 UTF-8 bytes)')
    args = parser.parse_args()
    from core.transfer_protocol import EncryptedCodec, new_message_id, validate_payload
    if args.send is not None and not args.device:
        parser.error('--send requires --device')
    try:
        if args.send is not None:
            validate_payload(dict(v=1, kind='text', id=new_message_id(),
                                  ts=int(time.time()), text=args.send))
        key = getpass('Shared pairing key (64 hex characters): ') if args.device else None
        if args.device:
            EncryptedCodec(key)  # Empty and malformed keys fail before radio access.
    except (ValueError, UnicodeError) as error:
        parser.error(str(error))
    from PySide6.QtCore import QCoreApplication, QTimer
    from core.ble_transfer import BleTextClient
    app = QCoreApplication([])
    client = BleTextClient()
    selected = [False]
    client.status.connect(print)

    def found(identity, name, rssi):
        print(f'{identity}  {name}  RSSI {rssi} dBm')
        if args.device and identity == args.device and not selected[0]:
            selected[0] = True
            QTimer.singleShot(0, lambda: client.connect_device(identity, key))

    client.discovered.connect(found)
    client.scan_finished.connect(lambda: app.quit() if args.scan else None)
    client.ready.connect(lambda: client.send_text(args.send) if args.send else print('Connected; no text requested'))
    client.delivered.connect(lambda _: (print('Peer acknowledged receipt'), app.quit()))
    client.failed.connect(lambda _, reason: (print(reason), app.exit(1)))
    QTimer.singleShot(60000, lambda: app.exit(1))
    client.scan()
    result = app.exec()
    client.stop()
    return result


if __name__ == '__main__':
    sys.exit(main())
