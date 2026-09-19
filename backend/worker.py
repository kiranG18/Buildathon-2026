"""Worker entrypoint: python -m backend.worker"""

import signal

from backend.core import logging as clog
from backend.core.config import get_settings
from backend.orchestrator.worker import Worker


def main() -> None:
    clog.setup(get_settings().log_level)
    w = Worker()
    signal.signal(signal.SIGTERM, lambda *_: w.stop())
    w.run_forever()


if __name__ == "__main__":
    main()
