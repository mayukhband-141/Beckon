import asyncio
import http
import json
import urllib.request
import numpy as np
from daemon.app.config import DaemonConfig
from daemon.app.ring_buffer import AudioRingBuffer
from daemon.app.server import BeckonServer
from daemon.summary.catchup import CatchUpSummarizer


def test_audio_ring_buffer():
    rb = AudioRingBuffer(sample_rate=16000, capacity_sec=5.0)
    assert rb.total_samples_written == 0

    # Write 1 second of 16kHz audio (16000 samples = 32000 bytes)
    samples = np.zeros(16000, dtype=np.int16)
    rb.append_pcm16_bytes(samples.tobytes())
    assert rb.total_samples_written == 16000

    window = rb.get_last_n_seconds(1.0)
    assert len(window) == 16000

    # Test rolling transcripts
    rb.add_transcript("Hello team, can everyone hear me?", "Alex")
    context = rb.get_recent_transcript_context(10.0)
    assert "Alex: Hello team" in context


def test_daemon_config():
    cfg = DaemonConfig(port=9999, whisper_model="base")
    assert cfg.port == 9999
    assert cfg.whisper_model == "base"
    assert "balanced" in cfg.thresholds
    assert cfg.sample_rate == 16000


def test_catchup_summarizer_fallback():
    # When no key or url, summarizer returns raw snippet instantly
    summarizer = CatchUpSummarizer(groq_api_key="", ollama_url="")
    assert not summarizer.is_enabled
    res = summarizer.summarize("Alex", "Alex, could you take over screen sharing?")
    assert res == "Alex, could you take over screen sharing?"


async def run_server_protocol_test():
    test_port = 8799
    test_token = "secret_integration_token_42"
    cfg = DaemonConfig(
        host="127.0.0.1",
        port=test_port,
        auth_token=test_token,
        enable_loopback=False,
        enable_kws=False
    )
    server = BeckonServer(config=cfg)

    import websockets

    # Start WebSocket server
    ws_server = await websockets.serve(
        server.handle_connection,
        cfg.host,
        cfg.port,
        process_request=server.process_http_request,
        max_size=10 * 1024 * 1024
    )

    def fetch_http(url):
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            return resp.status, resp.read()

    try:
        # 1. Test HTTP /ping in worker thread so event loop is not blocked
        status, body = await asyncio.to_thread(fetch_http, f"http://127.0.0.1:{test_port}/ping")
        assert status == 200
        assert b"OK" in body

        # 2. Test HTTP /pair in worker thread
        status, body = await asyncio.to_thread(fetch_http, f"http://127.0.0.1:{test_port}/pair")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert data["service"] == "beckon"
        assert data["port"] == test_port
        # Verify token is NOT exposed in pairing JSON
        assert "token" not in data

        # 3. Test unauthorized WebSocket connection without token
        unauth_closed = False
        try:
            async with websockets.connect(f"ws://127.0.0.1:{test_port}") as ws:
                # Send an invalid token message so server immediately rejects
                await ws.send(json.dumps({"type": "auth", "token": "wrong_token"}))
                await ws.recv()
        except websockets.exceptions.ConnectionClosed as e:
            assert e.rcvd.code == 4001 or e.code == 4001
            unauth_closed = True
        assert unauth_closed, "Unauthorized connection should have been closed with code 4001"

        # 4. Test authorized connection via Authorization header
        headers = {"Authorization": f"Bearer {test_token}"}
        async with websockets.connect(f"ws://127.0.0.1:{test_port}", additional_headers=headers) as ws:
            # First message should be 'welcome'
            welcome_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            welcome_data = json.loads(welcome_msg)
            assert welcome_data["type"] == "welcome"
            assert welcome_data["sample_rate"] == 16000

            # Ping/Pong test
            await ws.send(json.dumps({"type": "ping", "timestamp": 12345}))
            pong_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            pong_data = json.loads(pong_msg)
            assert pong_data["type"] == "pong"
            assert pong_data["timestamp"] == 12345

            # Config Update test
            await ws.send(json.dumps({
                "type": "config_update",
                "canonical_name": "Sarah",
                "aliases": ["Sara"],
                "sensitivity": "strict"
            }))
            ack_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            ack_data = json.loads(ack_msg)
            assert ack_data["type"] == "config_ack"
            assert ack_data["status"] == "ok"
            assert "Sarah" in server.config.name_profile.all_names

            # Test Evaluate test
            await ws.send(json.dumps({
                "type": "test_evaluate",
                "text": "Hey Sarah, can you review the slides?"
            }))
            eval_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            eval_data = json.loads(eval_msg)
            assert eval_data["type"] == "test_evaluate_result"
            assert eval_data["matched"] is True
            assert eval_data["target_name"] == "Sarah"

            # Streaming audio chunk test
            audio_chunk = np.zeros(1600, dtype=np.int16).tobytes()
            await ws.send(audio_chunk)
            await asyncio.sleep(0.1)
            assert server.ring_buffer.total_samples_written >= 1600

        # 5. Test authorized connection via query string ?token=...
        async with websockets.connect(f"ws://127.0.0.1:{test_port}/?token={test_token}") as ws:
            welcome_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            welcome_data = json.loads(welcome_msg)
            assert welcome_data["type"] == "welcome"

        print("All Beckon Server Protocol Integration Tests Passed!")

    finally:
        ws_server.close()
        await ws_server.wait_closed()


def test_server_protocol():
    asyncio.run(run_server_protocol_test())


if __name__ == "__main__":
    test_audio_ring_buffer()
    test_daemon_config()
    test_catchup_summarizer_fallback()
    test_server_protocol()
