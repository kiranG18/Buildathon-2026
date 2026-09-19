"""Export the agent output JSON Schemas (pasted into DronaHQ Structured Output) and the OpenAPI document."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.models import MODELS, flatten_schema  # noqa: E402


def main() -> None:
    out = ROOT / "agents" / "schemas"
    out.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        (out / f"{name}.json").write_text(json.dumps(flatten_schema(model.model_json_schema()), indent=2) + "\n", encoding="utf-8")
    from backend.main import app

    (ROOT / "docs" / "openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print("wrote", len(MODELS), "schemas and docs/openapi.json")


if __name__ == "__main__":
    main()
