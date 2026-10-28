"""Live integration check over real HTTP + WebSockets, against a local or deployed server.

  python scripts/check_multiplayer.py                       # http://127.0.0.1:8765
  python scripts/check_multiplayer.py https://your-app.example.com

Two independent clients create/join a room, verify ownership enforcement, chat and
hints, solve all three rounds cooperatively, then replay. Also checks the AI crew
and clean rejection of an unknown room. Exits non-zero on any failure.
"""
import asyncio
import json
import sys
import time

import httpx
from websockets.asyncio.client import connect

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from game_logic import rotate, solve  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765').rstrip('/')
WS = BASE.replace('https://', 'wss://').replace('http://', 'ws://')


async def receive(ws, predicate, timeout=12):
    limit = time.monotonic() + timeout
    while True:
        seconds = limit - time.monotonic()
        if seconds <= 0:
            raise AssertionError('Timed out waiting for state')
        data = json.loads(await asyncio.wait_for(ws.recv(), seconds))
        if data.get('type') == 'error' and data.get('fatal'):
            raise AssertionError(f'Server error: {data}')
        if predicate(data):
            return data


def is_state(pred):
    return lambda m: m.get('type') == 'state' and pred(m)


async def join(code, name):
    ws = await connect(f'{WS}/ws/{code}')
    await ws.send(json.dumps({'type': 'join', 'name': name}))
    return ws, await receive(ws, is_state(lambda s: True))


async def main():
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=15) as http:
        health = (await http.get(f'{BASE}/health')).json()
        assert health['ok'] is True
        print(f"PASS: health ok (server {health.get('version', '?')})")
        assert (await http.get(f'{BASE}/')).status_code == 200
        code = (await http.post(f'{BASE}/api/rooms')).raise_for_status().json()['code']
        solo_code = (await http.post(f'{BASE}/api/rooms')).raise_for_status().json()['code']

    async with connect(f'{WS}/ws/ZZZZZ') as ghost:
        msg = json.loads(await ghost.recv())
        assert msg['type'] == 'error' and msg['fatal']
    print('PASS: unknown room rejected with a fatal error')

    a, va = await join(code, 'Nova')
    b, vb = await join(code, 'Orion')
    try:
        va = await receive(a, is_state(lambda s: len(s['players']) == 2))
        assert va['you'] != vb['you'] and va['host'] == va['you']
        assert va['owners'] == [va['you'], vb['you'], va['you'], vb['you']]
        print(f'PASS: two independent clients joined room {code}')

        await a.send(json.dumps({'type': 'start'}))
        va = await receive(a, is_state(lambda s: s['phase'] == 'playing'))
        vb = await receive(b, is_state(lambda s: s['phase'] == 'playing'))
        assert va['positions'] == vb['positions'] and va['target'] == vb['target']
        print('PASS: game starts with synchronized state')

        original = va['positions']
        await b.send(json.dumps({'type': 'move', 'dial': 0, 'direction': 1}))
        err = await receive(b, lambda m: m.get('type') == 'error')
        assert 'teammate' in err['message']
        await b.send(json.dumps({'type': 'chat', 'message': 'Testing unauthorized move'}))
        va = await receive(a, is_state(lambda s: any(m['message'] == 'Testing unauthorized move' for m in s['chat'])))
        assert va['positions'] == original
        print('PASS: server rejects unauthorized movement; chat syncs')

        await a.send(json.dumps({'type': 'hint'}))
        va = await receive(a, is_state(lambda s: s['hints'] == 1))
        print('PASS: hint delivered and counted')

        for stage in range(1, 4):
            if stage > 1:
                va = await receive(a, is_state(lambda s: s['phase'] == 'playing' and s['stage'] == stage), timeout=20)
                vb = await receive(b, is_state(lambda s: s['phase'] == 'playing' and s['stage'] == stage), timeout=20)
            steps = solve(va['positions'], va['target'])
            for dial, direction in steps:
                actor = a if va['owners'][dial] == va['you'] else b
                expected = rotate(va['positions'], dial, direction)
                await actor.send(json.dumps({'type': 'move', 'dial': dial, 'direction': direction}))
                va = await receive(a, is_state(lambda s: s['positions'] == expected or s['phase'] != 'playing'))
                vb = await receive(b, is_state(lambda s: s['positions'] == expected or s['phase'] != 'playing'))
                assert va['positions'] == vb['positions']
                await asyncio.sleep(.15)
            assert va['result'] == vb['result'] == 'solved', (va['phase'], va['result'])
            assert va['score'] == vb['score'] > 0
            assert va['phase'] == ('finished' if stage == 3 else 'intermission')
            print(f'PASS: round {stage} solved in {len(steps)} moves (par {va["history"][-1]["par"]}); score {va["score"]}')

        await a.send(json.dumps({'type': 'start'}))
        await receive(a, is_state(lambda s: s['phase'] == 'playing' and s['stage'] == 1 and s['score'] == 0))
        await receive(b, is_state(lambda s: s['phase'] == 'playing' and s['stage'] == 1 and s['score'] == 0))
        print('PASS: replay resets score and starts fresh round')
    finally:
        await a.close()
        await b.close()

    solo, vs = await join(solo_code, 'Solo')
    try:
        await solo.send(json.dumps({'type': 'add_bot'}))
        vs = await receive(solo, is_state(lambda s: len(s['players']) == 2))
        await solo.send(json.dumps({'type': 'start'}))
        vs = await receive(solo, is_state(lambda s: s['phase'] == 'playing'))
        deadline = time.monotonic() + 60
        while vs['phase'] == 'playing' and time.monotonic() < deadline:
            mine = [m for m in solve(vs['positions'], vs['target']) if vs['owners'][m[0]] == vs['you']]
            if mine:
                await solo.send(json.dumps({'type': 'move', 'dial': mine[0][0], 'direction': mine[0][1]}))
                await asyncio.sleep(.2)
            vs = await receive(solo, is_state(lambda s: True))
        assert vs['result'] == 'solved', vs['phase']
        print('PASS: player + AI crewmate solved a round together')
    finally:
        await solo.close()
    print(f'MULTIPLAYER INTEGRATION: ALL CHECKS PASSED ({time.monotonic() - started:.1f}s against {BASE})')


if __name__ == '__main__':
    asyncio.run(main())
