from util.config import load_config
from util.logging_config import setup_logging
from tui.app import NaseApp


def main() -> None:
    logger = setup_logging()
    logger.info("NASE starting")

    config = load_config()

    app = NaseApp(config)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("NASE shutting down")


if __name__ == "__main__":
    main()
