"""Rebuild the schema from scratch and reload the seeded demo workspace."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.db import migrate  # noqa: E402
from scripts.load_seed import load  # noqa: E402


def main() -> None:
    t = time.monotonic()
    migrate(reset=True)
    print("loaded", load())
    print(f"reset finished in {time.monotonic() - t:.1f}s")


if __name__ == "__main__":
    main()
