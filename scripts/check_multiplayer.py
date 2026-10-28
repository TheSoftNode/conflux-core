"""Integration test over real HTTP/WebSockets against a locally running game server.
Start: uvicorn server:app --host 127.0.0.1 --port 8765 --workers 1
Then: python scripts/check_multiplayer.py
"""
import asyncio
import json
import time

import httpx
from websockets.asyncio.client import connect

BASE='http://127.0.0.1:8765'

async def receive(ws,predicate,timeout=8):
    limit=time.monotonic()+timeout
    while True:
        seconds=limit-time.monotonic()
        if seconds <= 0: raise AssertionError('Timed out waiting for state')
        data=json.loads(await asyncio.wait_for(ws.recv(),seconds))
        if data.get('type')=='error': raise AssertionError(f"Server error: {data}")
        if predicate(data):return data

def rotate(positions,i,direction):
    ans=positions[:]
    ans[i]=(ans[i]+direction)%6
    ans[(i+1)%4]=(ans[(i+1)%4]-direction)%6
    return ans

def shortest_moves(target,positions):
    diffs=[(target[i]-positions[i])%6 for i in range(4)]
    candidates=[]
    for last in range(6):
        d=[];previous=last
        for delta in diffs:
            current=(delta+previous)%6
            d.append(current);previous=current
        if d[-1] == last:
            signed=[n if n<=3 else n-6 for n in d]
            candidates.append((sum(abs(n) for n in signed),signed))
    assert candidates,'Puzzle is unreachable under the coupled movement rules'
    ds=min(candidates)[1]
    return [(i,1 if n>0 else -1) for i,n in enumerate(ds) for _ in range(abs(n))]

async def main():
    async with httpx.AsyncClient(timeout=10) as http:
        r=await http.post(f'{BASE}/api/rooms')
        r.raise_for_status();code=r.json()['code']
    async with connect(f'ws://127.0.0.1:8765/ws/{code}') as a:
        await a.send(json.dumps({'type':'join','name':'Nova'}))
        va=await receive(a,lambda s:s.get('phase')=='lobby' and len(s.get('players',[]))==1)
        async with connect(f'ws://127.0.0.1:8765/ws/{code}') as b:
            await b.send(json.dumps({'type':'join','name':'Orion'}))
            va=await receive(a,lambda s:len(s.get('players',[]))==2)
            vb=await receive(b,lambda s:len(s.get('players',[]))==2)
            assert va['you']!=vb['you']
            assert va['host']==va['you']
            assert va['owners']==[va['you'],vb['you'],va['you'],vb['you']]
            print(f'PASS: two independent clients joined room {code}')
            await a.send(json.dumps({'type':'start'}))
            va=await receive(a,lambda s:s.get('phase')=='playing')
            vb=await receive(b,lambda s:s.get('phase')=='playing')
            assert va['positions']==vb['positions']
            print('PASS: game starts with synchronized state')
            # Try unauthorized move by the second player on first player's station.
            original=va['positions'][:]
            await b.send(json.dumps({'type':'move','dial':0,'direction':1}))
            await asyncio.sleep(.3)
            assert va['positions']==original  # No update expected.
            # This isn't merely checking our stale copy: get a snapshot by sending chat.
            await b.send(json.dumps({'type':'chat','message':'Testing unauthorized move'}))
            va=await receive(a,lambda s:any(m['message']=='Testing unauthorized move' for m in s.get('chat',[])))
            vb=await receive(b,lambda s:any(m['message']=='Testing unauthorized move' for m in s.get('chat',[])))
            assert va['positions']==original
            print('PASS: server rejects unauthorized movement; chat syncs')
            for stage in range(1,4):
                if stage>1:
                    va=await receive(a,lambda s:s.get('phase')=='playing' and s.get('stage')==stage,timeout=12)
                    vb=await receive(b,lambda s:s.get('phase')=='playing' and s.get('stage')==stage,timeout=12)
                steps=shortest_moves(va['target'],va['positions'])
                print(f'STAGE {stage}: {len(steps)} legal rotations needed')
                for dial,direction in steps:
                    actor=a if va['owners'][dial]==va['you'] else b
                    expected=rotate(va['positions'],dial,direction)
                    before=va['revision']
                    await actor.send(json.dumps({'type':'move','dial':dial,'direction':direction}))
                    va=await receive(a,lambda s:s.get('revision',-1)>before and s.get('positions')==expected)
                    vb=await receive(b,lambda s:s.get('revision',-1)>before and s.get('positions')==expected)
                    assert va['positions']==vb['positions']
                    await asyncio.sleep(.14)
                assert va['result']=='solved' and vb['result']=='solved', (va['phase'],va['result'])
                assert va['score']==vb['score'] and va['score']>0
                assert va['phase'] == ('finished' if stage==3 else 'intermission')
                print(f'PASS: round {stage} solved and synchronized; cumulative score {va["score"]}')
            await a.send(json.dumps({'type':'start'}))
            va=await receive(a,lambda s:s.get('phase')=='playing' and s.get('stage')==1 and s.get('score')==0)
            vb=await receive(b,lambda s:s.get('phase')=='playing' and s.get('stage')==1 and s.get('score')==0)
            print('PASS: replay resets score and starts fresh round')
            print('MULTIPLAYER INTEGRATION: ALL CHECKS PASSED')

if __name__=='__main__':asyncio.run(main())
