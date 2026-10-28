"""Concurrency smoke test: many rooms with two players each, all moving at once.

  python scripts/load_test.py [base-url] [rooms]

Reports move -> broadcast round-trip latency. Use a local server with a raised
creation limit, e.g. CONFLUX_CREATE_LIMIT=1000 uvicorn server:app --port 8765.
"""
import asyncio
import json
import statistics
import sys
import time

import httpx
from websockets.asyncio.client import connect

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765').rstrip('/')
ROOMS = int(sys.argv[2]) if len(sys.argv) > 2 else 50
WS = BASE.replace('https://', 'wss://').replace('http://', 'ws://')
MOVES = 20


async def until(ws, pred, timeout=15):
    end = time.monotonic() + timeout
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), end - time.monotonic()))
        if pred(m):
            return m


async def room(http, latencies):
    code = (await http.post(f'{BASE}/api/rooms')).raise_for_status().json()['code']
    a = await connect(f'{WS}/ws/{code}')
    b = await connect(f'{WS}/ws/{code}')
    try:
        await a.send(json.dumps({'type': 'join', 'name': 'A'}))
        await until(a, lambda m: m.get('type') == 'state')
        await b.send(json.dumps({'type': 'join', 'name': 'B'}))
        await until(a, lambda m: m.get('type') == 'state' and len(m['players']) == 2)
        await a.send(json.dumps({'type': 'start'}))
        s = await until(a, lambda m: m.get('type') == 'state' and m['phase'] == 'playing')
        mine = s['owners'].index(s['you'])
        direction = 1
        for _ in range(MOVES):
            if s['phase'] != 'playing':
                break
            rev = s['revision']
            t0 = time.perf_counter()
            await a.send(json.dumps({'type': 'move', 'dial': mine, 'direction': direction}))
            s = await until(a, lambda m: m.get('type') == 'state' and (m['revision'] > rev))
            latencies.append((time.perf_counter() - t0) * 1000)
            direction = -direction
            await asyncio.sleep(0.15)
    finally:
        await a.close()
        await b.close()


async def main():
    latencies = []
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=20, limits=httpx.Limits(max_connections=200)) as http:
        results = await asyncio.gather(*(room(http, latencies) for _ in range(ROOMS)), return_exceptions=True)
    failures = [r for r in results if isinstance(r, Exception)]
    latencies.sort()
    print(f'{ROOMS} rooms / {ROOMS * 2} sockets, {len(latencies)} moves in {time.monotonic() - started:.1f}s')
    print(f'move->broadcast latency ms: median {statistics.median(latencies):.1f}, '
          f'p95 {latencies[int(len(latencies) * .95)]:.1f}, max {latencies[-1]:.1f}')
    print(f'failures: {len(failures)} {failures[:3]}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    asyncio.run(main())
