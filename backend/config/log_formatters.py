# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Structured (JSON-per-line) log formatting for production.

Written against the standard library rather than adding a dependency such as
python-json-logger: the whole requirement is one class, and every extra package
in the image is extra supply-chain surface for no benefit.

One JSON object per line is the format log shippers (Loki, Elastic, CloudWatch)
parse without configuration, and `docker compose logs` still shows it readably.
"""

import json
import logging


class JsonFormatter(logging.Formatter):
    """Renders a LogRecord as a single-line JSON object.

    Exception information is included under "exc_info" so tracebacks remain in
    the operator's logs — they are deliberately never sent to the user, which is
    a separate concern handled by DEBUG=False and the orchestrator's generic
    error message.
    """

    # Attributes LogRecord always carries; anything else a caller attached via
    # `extra=` is treated as structured context worth emitting.
    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        # Anything passed as logger.info("...", extra={"question_id": 7}).
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value

        # default=str so a stray UUID/datetime in `extra` degrades to a string
        # rather than raising inside the logging subsystem.
        return json.dumps(payload, default=str, ensure_ascii=False)
