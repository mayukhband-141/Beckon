import asyncio
import logging
import sys
import argparse
from daemon.app.config import DaemonConfig
from daemon.app.server import BeckonServer

class WebsocketsPingFilter(logging.Filter):
    def filter(self, record):
        # Suppress websockets' misleading internal message when plain HTTP health probes are answered with 200 OK
        return "connection rejected (200 OK)" not in record.getMessage()

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("websockets.server").addFilter(WebsocketsPingFilter())

def main():
    parser = argparse.ArgumentParser(description="Beckon Meeting Audio Daemon")
    parser.add_argument("--host", default=None, help="Host address to bind (defaults to 127.0.0.1 or BECKON_HOST)")
    parser.add_argument("--lan", action="store_true", help="Bind to 0.0.0.0 to allow companion devices on local network")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--model", default=None, help="Whisper model (tiny, base, small, medium)")
    parser.add_argument("--groq-key", default=None, help="Groq API key for catch-up summary notifications")
    parser.add_argument("--ollama-url", default=None, help="Ollama endpoint URL (e.g. http://localhost:11434)")
    parser.add_argument("--confidence", type=float, default=None, help="Minimum word confidence (default 0.40)")
    parser.add_argument("--name", default=None, help="Target user's name (defaults to BECKON_TARGET_NAME or 'Alex')")
    parser.add_argument("--aliases", nargs="*", default=None, help="Aliases list")
    parser.add_argument("--languages", nargs="*", default=None, help="Allowed language codes for speech recognition (e.g. --languages en bn hi)")
    parser.add_argument("--sensitivity", default=None, choices=["strict", "balanced", "sensitive"], help="Sensitivity level")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("beckon.main")
    logger.info("Initializing Beckon Daemon...")
    from daemon.app.config import LOADED_ENV_PATH
    if LOADED_ENV_PATH:
        logger.info("Loaded environment configuration from: %s", LOADED_ENV_PATH)
    else:
        logger.info("No .env file found; using system environment and default values.")

    config = DaemonConfig(port=args.port)
    if args.model:
        config.whisper_model = args.model
    if args.groq_key:
        config.groq_api_key = args.groq_key
    if args.ollama_url:
        config.ollama_url = args.ollama_url
    if args.confidence is not None:
        config.min_word_confidence = args.confidence

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

