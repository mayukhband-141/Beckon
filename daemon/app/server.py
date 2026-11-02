import asyncio
import http
import json
import logging
from typing import Set, Optional
import websockets
from websockets.server import WebSocketServerProtocol
from daemon.app.config import DaemonConfig
from daemon.app.ring_buffer import AudioRingBuffer
from daemon.speaker.tracker import SpeakerTracker
from daemon.app.pipeline import DetectionPipeline

logger = logging.getLogger("beckon.server")

class BeckonServer:
    def __init__(self, config: Optional[DaemonConfig] = None):
        self.config = config or DaemonConfig()
        self.ring_buffer = AudioRingBuffer(
            sample_rate=self.config.sample_rate,
            capacity_sec=self.config.ring_buffer_sec
        )
        self.speaker_tracker = SpeakerTracker()
        self.connected_clients: Set[WebSocketServerProtocol] = set()
        self.current_audio_source: Optional[WebSocketServerProtocol] = None

        self.pipeline = DetectionPipeline(
            config=self.config,
            ring_buffer=self.ring_buffer,
            speaker_tracker=self.speaker_tracker,
            on_alert_callback=self.broadcast_alert,
            on_transcript_callback=self.broadcast_transcript
        )

    async def broadcast_alert(self, alert_data: dict):
        message = json.dumps(alert_data)
        logger.info(f"Broadcasting alert to {len(self.connected_clients)} clients: {alert_data.get('name')}")
        if self.connected_clients:
            await asyncio.gather(
                *[client.send(message) for client in self.connected_clients],
                return_exceptions=True
            )

    async def broadcast_transcript(self, transcript_data: dict):
        message = json.dumps(transcript_data)
        if self.connected_clients:
            await asyncio.gather(
                *[client.send(message) for client in self.connected_clients],
                return_exceptions=True
            )

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        logger.info(f"New client connected from {websocket.remote_address}")
        self.connected_clients.add(websocket)
        authenticated = True  # Can enforce token verification

        try:
            # Send initial greeting & config
            await websocket.send(json.dumps({
                "type": "welcome",
                "sample_rate": self.config.sample_rate,
                "names": self.config.name_profile.all_names,
                "sensitivity": self.config.name_profile.sensitivity,
                "model": self.config.whisper_model
            }))

            async for message in websocket:
                if isinstance(message, bytes):
                    # PCM16 16kHz mono audio frame from client
                    self.current_audio_source = websocket
                    self.ring_buffer.append_pcm16_bytes(message)
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "speaker_update":
                            spk = data.get("active_speaker")
                            roster = data.get("roster")
                            self.speaker_tracker.update_active_speaker(spk, roster)

                        elif msg_type == "config_update":
                            canonical_name = data.get("canonical_name", self.config.name_profile.canonical_name)
                            aliases = data.get("aliases", self.config.name_profile.aliases)
                            sensitivity = data.get("sensitivity", self.config.name_profile.sensitivity)
                            self.pipeline.update_name_profile(canonical_name, aliases, sensitivity)
                            await websocket.send(json.dumps({"type": "config_ack", "status": "ok"}))

                        elif msg_type == "ping":
                            await websocket.send(json.dumps({
                                "type": "pong",
                                "timestamp": data.get("timestamp", data.get("time"))
                            }))

                        elif msg_type == "test_evaluate":
                            test_text = data.get("text", "")
                            match = self.pipeline.name_matcher.evaluate_text(test_text)
                            await websocket.send(json.dumps({
                                "type": "test_evaluate_result",
                                "text": test_text,
                                "matched": bool(match and match.matched),
                                "target_name": match.target_name if match else None,
                                "detected_phrase": match.detected_phrase if match else None,
                                "score": match.score if match else 0.0,
                                "cue_boost": match.cue_boost if match else 0.0
                            }))

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON message received: {message[:100]}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("Client connection closed.")
        finally:
            if self.current_audio_source == websocket:
                self.current_audio_source = None
            self.connected_clients.discard(websocket)

    def process_http_request(self, connection, request):
        """Intercept plain HTTP health/ping probes cleanly without breaking WebSocket handshakes."""
        upgrade_header = request.headers.get("Upgrade", "").lower()
        if "websocket" in upgrade_header:
            # Let WebSocket connection proceed with handshake
            return None

        # Only intercept non-WebSocket plain HTTP GET requests (e.g. socket pings)
        if request.path in ("/", "/ping", "/health"):
            remote = getattr(connection, "remote_address", "client")
            logger.info("Probe ping received from %s -> responded HTTP 200 OK", remote)
            return connection.respond(http.HTTPStatus.OK, "OK\n")
        return None

    async def start(self):
        logger.info(f"Starting Beckon Daemon on ws://{self.config.host}:{self.config.port}")
        server = await websockets.serve(
            self.handle_connection,
            self.config.host,
            self.config.port,
            process_request=self.process_http_request,
            max_size=10 * 1024 * 1024  # 10MB max message size
        )
        pipeline_task = asyncio.create_task(self.pipeline.run_loop())
        await asyncio.gather(server.wait_closed(), pipeline_task)
