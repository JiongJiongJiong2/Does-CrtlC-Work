"""Single-machine native radio smoke check; no clipboard, pairing or sending."""
import asyncio
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.nearby_peers import process_instance_id
from core.windows_nearby import WinRTNearbyBackend


async def main():
    stop = threading.Event()
    observed = {'available': False, 'app_peer_observations': 0}

    def emit(kind, values):
        if kind == 'availability':
            observed['available'] = values[0]
            observed['status'] = values[1]
            print(json.dumps({'event': kind, 'available': values[0], 'status': values[1]}, ensure_ascii=False), flush=True)
        elif kind == 'peer':
            observed['app_peer_observations'] += 1

    backend = WinRTNearbyBackend(process_instance_id(), emit)
    task = asyncio.create_task(backend.run(stop))
    try:
        await asyncio.wait_for(asyncio.shield(task), 6)
    except asyncio.TimeoutError:
        stop.set()
        await asyncio.wait_for(task, 2)
    except Exception as error:
        observed['error'] = f'{type(error).__name__}: {error}'
    finally:
        stop.set()
        backend.close()
    print(json.dumps(observed, ensure_ascii=False), flush=True)
    return 0 if observed['available'] and 'error' not in observed else 1


sys.exit(asyncio.run(main()))
