import logging
import json
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        if hasattr(record, "source"):
            payload["source"] = record.source
        for key in ("duration_ms", "pairs", "opportunities", "status", "url"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def setup_logging(log_file: str = "nase.log") -> logging.Logger:
    logger = logging.getLogger("nase")
    logger.setLevel(os.getenv("NASE_LOG_LEVEL", "INFO"))
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("NASE [%(levelname)s] %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger
