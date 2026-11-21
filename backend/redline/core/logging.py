import logging
import re


REDACT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"api_key=\S+"),
    re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern in REDACT_PATTERNS:
                msg = pattern.sub("[REDACTED]", msg)
            record.msg = msg
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level)
    root = logging.getLogger()
    root.addFilter(RedactFilter())
