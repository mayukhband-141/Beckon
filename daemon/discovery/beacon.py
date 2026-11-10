import asyncio
import json
import logging
import socket
from typing import Optional, Dict

logger = logging.getLogger("beckon.discovery")

def get_local_ip() -> str:
    """
    Determines the primary local IPv4 address connected to the LAN
    by querying the routing table without sending any actual network packets.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually connect, just probes OS routing table
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class UDPDiscoveryBeacon:
    """
    Tier 5: Local Network Discovery Beacon & Pairer.
    Enables zero-configuration pairing between the Beckon Python Daemon
    and Android Companion App / Chrome Extension on the same local Wi-Fi.
    Broadcasts UDP beacons on port 8766 and replies to active discovery probes.
    """

    BROADCAST_PORT = 8766

    def __init__(self, ws_port: int = 8765, auth_token: str = "", service_name: str = "Beckon Daemon"):
        self.ws_port = ws_port
        self.auth_token = auth_token
        self.service_name = service_name
        self.local_ip = get_local_ip()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    def get_pairing_payload(self) -> Dict:
        return {
            "service": "beckon",
            "version": "1.0",
            "name": self.service_name,
            "host": self.local_ip,
            "port": self.ws_port,
            "ws_url": f"ws://{self.local_ip}:{self.ws_port}",
            "token": self.auth_token,
        }

    def print_terminal_card(self):
        """Prints a pairing card in the console on daemon launch."""
        ip = self.local_ip
        port = self.ws_port
        url = f"ws://{ip}:{port}"
        pair_url = f"http://{ip}:{port}/pair"

        box_width = 62
        print("\n" + "=" * box_width)
        print(" " * 18 + "BECKON PAIRING CARD")
        print("=" * box_width)
        print(f"  • Local IP Address:   {ip}")
        print(f"  • WebSocket Endpoint: {url}")
        print(f"  • HTTP Pairing Info:  {pair_url}")
        print(f"  • Auto-Discovery:     Active on UDP Port {self.BROADCAST_PORT}")
        print("-" * box_width)
        print("  [Android App] Tap 'Auto-Detect' on the same Wi-Fi,")
        print(f"                or enter: {ip}:{port}")
        print("=" * box_width + "\n")

    async def _broadcast_loop(self):
        """Periodically broadcasts discovery beacon packets to the local subnet."""
        loop = asyncio.get_running_loop()

        # Create UDP broadcast socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)

        try:
            sock.bind(("", self.BROADCAST_PORT))
        except Exception as e:
            logger.debug("Could not bind receiver on UDP %d (%s), continuing broadcast-only", self.BROADCAST_PORT, e)

        payload_bytes = json.dumps(self.get_pairing_payload()).encode("utf-8")
        broadcast_addr = ("255.255.255.255", self.BROADCAST_PORT)

        logger.info("UDP Discovery Beacon active on port %d (Broadcasting to LAN)", self.BROADCAST_PORT)

        try:
            while self.is_running:
                # 1. Send broadcast beacon
                try:
                    await loop.sock_sendto(sock, payload_bytes, broadcast_addr)
                except Exception as e:
                    logger.debug("UDP broadcast send failed: %s", e)

                # 2. Check for incoming query probes without blocking
                try:
                    data, addr = sock.recvfrom(1024)
                    if data:
                        # Reply with full pairing details
                        sock.sendto(payload_bytes, addr)
                        logger.debug("Replied to discovery probe from %s", addr)
                except (BlockingIOError, socket.error):
                    pass

                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            pass
        finally:
            sock.close()

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._broadcast_loop())

    def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
