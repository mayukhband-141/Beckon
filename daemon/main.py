import asyncio
import logging
import sys
import argparse
from daemon.app.config import DaemonConfig
from daemon.app.server import BeckonServer

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    parser = argparse.ArgumentParser(description="Beckon Meeting Audio Daemon")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--model", default="base", help="Whisper model (tiny, base, small)")
    parser.add_argument("--name", default="Mayukh", help="Target user's name")
    parser.add_argument("--aliases", nargs="*", default=["Mayuk", "Moyukh", "Mayukha"], help="Aliases")
    parser.add_argument("--sensitivity", default="balanced", choices=["strict", "balanced", "sensitive"], help="Sensitivity level")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("beckon.main")
    logger.info("Initializing Beckon Daemon...")

    config = DaemonConfig(
        host=args.host,
        port=args.port,
        whisper_model=args.model
    )
    config.name_profile.canonical_name = args.name
    config.name_profile.aliases = args.aliases
    config.name_profile.sensitivity = args.sensitivity

    server = BeckonServer(config=config)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user.")

if __name__ == "__main__":
    main()

