from fastapi.testclient import TestClient
from server import app, ROOMS


def test_create_and_health():
    with TestClient(app) as client:
        result = client.post('/api/rooms')
        assert result.status_code == 200
        assert len(result.json()['code']) == 5
        assert client.get('/health').json()['ok'] is True
        assert client.get('/').status_code == 200


def test_two_players_and_owner_protection():
    with TestClient(app) as client:
        code = client.post('/api/rooms').json()['code']
        with client.websocket_connect(f'/ws/{code}') as w1:
            w1.send_json({'type':'join','name':'Alpha'})
            one = w1.receive_json()
            assert one['phase']=='lobby'
            assert one['session'] != one['you']
            with client.websocket_connect(f'/ws/{code}') as w2:
                w2.send_json({'type':'join','name':'Beta'})
                # Update goes to both clients.
                one = w1.receive_json()
                two = w2.receive_json()
                assert len(one['players']) == 2
                assert one['you'] != two['you']
                assert one['session'] != two['session']
                assert one['host'] == one['you']
                # Public player ID is not a rejoin token.
                assert two['players'][0]['id'] != one['session']
                w1.send_json({'type':'start'})
                one = w1.receive_json()
                two = w2.receive_json()
                assert one['phase'] == two['phase'] == 'playing'
                assert one['positions'] == two['positions']
                assert set(one['owners']) == {one['you'],two['you']}
                mine = [i for i,t in enumerate(one['owners']) if t == one['you']]
                forbidden = next(i for i in range(4) if i not in mine)
                original = one['positions'][:]
                w1.send_json({'type':'move','dial':forbidden,'direction':1})
                assert ROOMS[code].puzzle.positions == original
                w1.send_json({'type':'move','dial':mine[0],'direction':1})
                updated_one = w1.receive_json()
                updated_two = w2.receive_json()
                assert updated_one['positions'] != original
                assert updated_one['positions'] == updated_two['positions']
