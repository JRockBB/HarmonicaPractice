import json
from http.client import HTTPConnection
from threading import Thread

import pytest

from harptab.cli import main
from harptab.core.assign import assign
from harptab.core.chords import assign_chords
from harptab.core.instrument import HarmonicaModel
from harptab.listener import load_session, make_server
from harptab.models import Arrangement, ChordEvent, ChordScore, Melody, NoteEvent, Technique
from harptab.render.chords import render_chord_json
from harptab.render.json import render_json


def test_listener_preserves_actual_chord_targets_and_source_timing(tmp_path):
    score = ChordScore([ChordEvent((71, 74, 78), 19, 0.4), ChordEvent((71, 74, 79), 21, 0.3)])
    for key, expected in [(7, [[78], [71, 74, 79]]), (9, [[71, 74, 78], [79]])]:
        path = tmp_path / f"{key}.json"
        arranged = assign_chords(score, HarmonicaModel(key), overblows=True)
        path.write_text(render_chord_json(score, arranged), encoding="utf-8")
        session = load_session(path)
        assert [e["pitches"] for e in session["events"]] == expected
        assert [e["start"] for e in session["events"]] == [0, 2]
        assert [e["sourceStart"] for e in session["events"]] == [19, 21]
        assert session["sourceStart"] == 19
        assert session["duration"] == pytest.approx(2.3)
        assert "50% speed" in session["guide"].replace("**", "")
        assert session["transpose"] == 0
        for event, voice in zip(session["events"], arranged.voicings, strict=True):
            assert event["actions"] == [
                {
                    "hole": a.hole,
                    "technique": a.technique.value,
                    "bend_semitones": a.bend_semitones,
                    "pitch": a.pitch,
                }
                for a in voice.actions
            ]
        if key == 9:
            assert session["fingerings"]["68"] == [
                {"tab": "-3", "instruction": "Draw (inhale) through hole 3"}
            ]
            assert session["fingerings"]["78"] == [
                {"tab": "-6", "instruction": "Draw (inhale) through hole 6"}
            ]


def test_melody_transposition_and_unplayable_gaps(tmp_path):
    melody = Melody([NoteEvent(48, 3, 0.3), NoteEvent(60, 4, 0.3)])
    arrangement = assign(melody, HarmonicaModel(0), transpose=12)
    path = tmp_path / "melody.json"
    path.write_text(render_json(melody, arrangement), encoding="utf-8")
    session = load_session(path)
    assert [e["pitches"] for e in session["events"]] == [[60], [72]]
    assert session["transpose"] == 12
    path.write_text(render_json(melody, assign(melody, HarmonicaModel(0))), encoding="utf-8")
    assert load_session(path)["events"][0]["pitches"] == []
    assert load_session(path)["events"][0]["actions"] == []


@pytest.mark.parametrize("key", range(12))
def test_hole_diagram_uses_selected_actions_in_every_harp_key(tmp_path, key):
    harp = HarmonicaModel(key)
    available = [action for pitch in range(128) for action in harp.actions_for_pitch(pitch)]
    actions = [next(a for a in available if a.technique == technique) for technique in Technique]
    melody = Melody(
        [NoteEvent(a.pitch, float(i), 0.25) for i, a in enumerate(actions)],
        source=r"C:\music\Another exercise.wav",
    )
    arrangement = Arrangement(key, 1, 0, actions, 0, {})
    path = tmp_path / "arrangement.json"
    path.write_text(render_json(melody, arrangement), encoding="utf-8")
    session = load_session(path)
    assert session["title"] == "Another exercise"
    assert [event["actions"][0] for event in session["events"]] == arrangement.to_dict()["actions"]
    assert [event["pitches"] for event in session["events"]] == [[a.pitch] for a in actions]


@pytest.mark.parametrize(
    "data", [{}, [], {"notes": []}, {"arrangement": {}}, {"score": {}, "arrangement": None}]
)
def test_invalid_sessions_report_friendly_errors(tmp_path, data, capsys):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data))
    assert main(["listen", str(path), "--no-browser"]) == 2
    assert "harptab listen:" in capsys.readouterr().err


def test_impossible_reeds_rejected(tmp_path):
    score = ChordScore([ChordEvent((60, 64, 67), 0, 1)])
    data = json.loads(render_chord_json(score, assign_chords(score, HarmonicaModel(0))))
    data["arrangement"]["voicings"][0]["actions"][0]["hole"] = 10
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="does not produce"):
        load_session(path)


def test_server_serves_only_bundled_assets_and_chosen_sessions():
    server = make_server([{"title": "private practice"}], port=0)
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        for route, mime in [
            ("/", "text/html"),
            ("/app.mjs", "text/javascript"),
            ("/pitch.mjs", "text/javascript"),
            ("/engine.mjs", "text/javascript"),
            ("/takes.mjs", "text/javascript"),
            ("/review.mjs", "text/javascript"),
            ("/style.css", "text/css"),
            ("/api/sessions", "application/json"),
        ]:
            connection.request("GET", route)
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type").startswith(mime)
            assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
            assert "media-src 'self' blob:" in response.getheader("Content-Security-Policy")
            body = response.read()
            assert body
            if route == "/api/sessions":
                assert json.loads(body)["sessions"][0]["title"] == "private practice"
        for route in ["/../pyproject.toml", "/sample/song.mp3", "/%2e%2e/README.md", "/anything"]:
            connection.request("GET", route)
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        connection.request("GET", "/api/sessions", headers={"Host": "other.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request("POST", "/api/sessions", body=b"audio")
        response = connection.getresponse()
        assert response.status == 501
        response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_cli_dispatch_and_no_browser(tmp_path, monkeypatch, capsys):
    melody = Melody([NoteEvent(60, 0, 1)])
    path = tmp_path / "practice.json"
    path.write_text(render_json(melody, assign(melody, HarmonicaModel(0))), encoding="utf-8")
    monkeypatch.setattr("harptab.listener.webbrowser.open", lambda _: pytest.fail("browser opened"))

    def stop(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("harptab.listener.ThreadingHTTPServer.serve_forever", stop)
    assert main(["listen", str(path), "--port", "0", "--no-browser"]) == 0
    assert "http://127.0.0.1:" in capsys.readouterr().out
