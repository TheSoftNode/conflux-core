from fastapi.testclient import TestClient
from server import app, ROOMS
from game_logic import rotate


def test_all_game_assets_are_served_without_a_cdn():
    with TestClient(app) as client:
        for path in ("/", "/static/app.js", "/static/scene.js", "/static/fallback.js", "/static/style.css", "/static/cover.png"):
            response = client.get(path)
            assert response.status_code == 200, path
        html = client.get('/').text
        assert "CONFLUX CORE" in html
        assert "cdn." not in html
        assert 'id="reactor-canvas"' in html


def test_player_can_finish_round_and_other_client_sees_result():
    with TestClient(app) as client:
        code = client.post('/api/rooms').json()['code']
        with client.websocket_connect(f'/ws/{code}') as a:
            a.send_json({'type': 'join', 'name': 'Nova'})
            first = a.receive_json()
            with client.websocket_connect(f'/ws/{code}') as b:
                b.send_json({'type': 'join', 'name': 'Mira'})
                first = a.receive_json()
                second = b.receive_json()
                a.send_json({'type': 'start'})
                first = a.receive_json()
                second = b.receive_json()
                owner = first['owners'][0]
                # Prepare a state exactly one valid rotation from the solution.
                puzzle = ROOMS[code].puzzle
                puzzle.positions = rotate(puzzle.target, 0, -1)
                if owner == first['you']:
                    actor = a
                else:
                    actor = b
                actor.send_json({'type': 'move', 'dial': 0, 'direction': 1})
                result_a = a.receive_json()
                result_b = b.receive_json()
                assert result_a['phase'] == result_b['phase'] == 'intermission'
                assert result_a['result'] == result_b['result'] == 'solved'
                assert result_a['last_score'] > 0
                assert result_a['score'] == result_b['score']
