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
from daemon.discovery.beacon import UDPDiscoveryBeacon
from daemon.audio.loopback import SystemAudioLoopback

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
        self.beacon = UDPDiscoveryBeacon(
            ws_port=self.config.port,
            auth_token=self.config.auth_token,
            service_name="Beckon Daemon"
        )
        self.loopback = None
        if self.config.enable_loopback:
            self.loopback = SystemAudioLoopback(
                sample_rate=self.config.sample_rate,
                on_pcm_callback=self._handle_loopback_pcm
            )

    def _handle_loopback_pcm(self, pcm_bytes: bytes):
        """Processes desktop loopback audio directly into ring buffer and fast-path KWS."""
        self.ring_buffer.append_pcm16_bytes(pcm_bytes)
        self.pipeline.handle_pcm_frame(pcm_bytes)

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

        # Origin validation: block arbitrary browser websites from DNS-rebinding / hijacking
        req = getattr(websocket, "request", None)
        origin = req.headers.get("Origin", "") if req else ""
        if origin and not (
            origin.startswith("chrome-extension://")
            or "localhost" in origin
            or "127.0.0.1" in origin
        ):
            logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
            await websocket.close(4003, "Forbidden Origin")
            return

        # Token auth: check Authorization header or query parameter
        token_found = ""
        if req:
            auth_val = req.headers.get("Authorization", "")
            if auth_val.startswith("Bearer "):
                token_found = auth_val[7:].strip()
            elif auth_val:
                token_found = auth_val.strip()
            if not token_found and "?" in req.path:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(req.path).query)
                token_found = qs.get("token", [""])[0]

        expected = self.config.auth_token
        authenticated = (not expected) or (token_found == expected)
        if not authenticated:
            await websocket.close(4001, "Unauthorized")
            return

        try:
            # Send initial greeting & config
            await websocket.send(json.dumps({
                "type": "welcome",
                "sample_rate": self.config.sample_rate,
                "names": self.config.name_profile.all_names,
                "sensitivity": self.config.name_profile.sensitivity,
                "model": self.config.whisper_model,
                "groq_enabled": self.pipeline.summarizer.is_enabled,
                "languages": self.config.languages
            }))

            async for message in websocket:
                if isinstance(message, bytes):
                    # PCM16 16kHz mono audio frame from client
                    if len(message) % 2 != 0:
                        message = message[:-1]  # drop trailing incomplete sample
                    self.current_audio_source = websocket
                    self.ring_buffer.append_pcm16_bytes(message)

                    # Tier 4: Fast-path acoustic evaluation
                    kws_event = self.pipeline.handle_pcm_frame(message)
                    if kws_event:
                        logger.debug("Acoustic KWS Fast-Path triggered (Score: %.2f)", kws_event.get("score", 0.0))
                elif isinstance(message, str):
                    if len(message) > 65536:  # 64KB text limit
                        logger.warning("Oversized text message dropped (%d bytes)", len(message))
                        continue
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

                            if "groq_api_key" in data:
                                self.config.groq_api_key = str(data["groq_api_key"]).strip()
                                self.pipeline.summarizer.groq_api_key = self.config.groq_api_key
                                logger.info("Updated Groq API Key from client UI (enabled=%s)", self.pipeline.summarizer.is_enabled)

                            if "ollama_url" in data:
                                url = str(data["ollama_url"]).strip()
                                if url.startswith(("http://localhost", "http://127.0.0.1", "http://0.0.0.0")):
                                    self.config.ollama_url = url
                                    self.pipeline.summarizer.ollama_url = url
                                else:
                                    logger.warning("Rejected non-local ollama_url: %s", url)
                                logger.info("Updated Ollama URL from client UI (enabled=%s)", self.pipeline.summarizer.is_enabled)

                            await websocket.send(json.dumps({
                                "type": "config_ack",
                                "status": "ok",
                                "groq_enabled": self.pipeline.summarizer.is_enabled
                            }))

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

        # Intercept plain HTTP pairing and health/ping requests
        if request.path in ("/", "/ping", "/health"):
            remote = getattr(connection, "remote_address", "client")
            logger.info("Probe ping received from %s -> responded HTTP 200 OK", remote)
            return connection.respond(http.HTTPStatus.OK, "OK\n")

        if request.path in ("/pair", "/info", "/status"):
            remote = getattr(connection, "remote_address", "client")
            logger.info("Pairing request received from %s -> responded pairing JSON", remote)
            pairing_json = json.dumps(self.beacon.get_pairing_payload(), indent=2)
            resp = connection.respond(http.HTTPStatus.OK, pairing_json)
            resp.headers["Content-Type"] = "application/json"
            return resp
        return None

    async def start(self):
        self.beacon.print_terminal_card()
        self.beacon.start()
        if self.loopback:
            self.loopback.start()

        logger.info(f"Starting Beckon Daemon on ws://{self.config.host}:{self.config.port}")
        server = await websockets.serve(
            self.handle_connection,
            self.config.host,
            self.config.port,
            process_request=self.process_http_request,
            ping_interval=15,
            ping_timeout=10,
            max_size=10 * 1024 * 1024  # 10MB max message size
        )
        pipeline_task = asyncio.create_task(self.pipeline.run_loop())
        try:
            await asyncio.gather(server.wait_closed(), pipeline_task)
        finally:
            self.beacon.stop()
            if self.loopback:
                self.loopback.stop()
            self.pipeline.stop()
            if not pipeline_task.done():
                pipeline_task.cancel()
                try:
                    await pipeline_task
                except asyncio.CancelledError:
                    pass
            if self.connected_clients:
                await asyncio.gather(
                    *[c.close(1001, "Server shutting down") for c in list(self.connected_clients)],
                    return_exceptions=True
                )
            server.close()
            await server.wait_closed()
