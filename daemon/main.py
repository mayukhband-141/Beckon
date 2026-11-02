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
    parser.add_argument("--host", default=None, help="Host address to bind (defaults to 127.0.0.1 or BECKON_HOST)")
    parser.add_argument("--lan", action="store_true", help="Bind to 0.0.0.0 to allow companion devices on local network")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--model", default="base", help="Whisper model (tiny, base, small)")
    parser.add_argument("--name", default=None, help="Target user's name (defaults to BECKON_TARGET_NAME or 'Alex')")
    parser.add_argument("--aliases", nargs="*", default=None, help="Aliases list")
    parser.add_argument("--languages", nargs="*", default=None, help="Allowed language codes for speech recognition (e.g. --languages en bn hi)")
    parser.add_argument("--sensitivity", default=None, choices=["strict", "balanced", "sensitive"], help="Sensitivity level")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("beckon.main")
    logger.info("Initializing Beckon Daemon...")

    config = DaemonConfig(
        port=args.port,
        whisper_model=args.model
    )

    if args.languages:
        config.languages = args.languages
    logger.info("Allowed recognition languages: %s", config.languages)

    if args.lan:
        config.host = "0.0.0.0"
        logger.warning("LAN mode active: Daemon bound to 0.0.0.0. Ensure local firewall rules protect port %d.", config.port)
    elif args.host:
        config.host = args.host

    if args.name:
        config.name_profile.canonical_name = args.name
    if args.aliases:
        config.name_profile.aliases = args.aliases
    if args.sensitivity:
        config.name_profile.sensitivity = args.sensitivity

    server = BeckonServer(config=config)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user.")

if __name__ == "__main__":
    main()

