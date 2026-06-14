from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.services.llm import LLMServiceError, build_llm_client  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("backend.app.services.llm").setLevel(logging.INFO)

    settings = get_settings()
    client = build_llm_client()
    model = getattr(client, "model", "unknown")
    provider = getattr(client, "provider", settings.llm_provider)

    print(f"Configured provider: {settings.llm_provider}")
    print(f"Instantiated client: {client.__class__.__name__}")
    print(f"Provider: {provider}")
    print(f"Model: {model}")

    try:
        response = client.generate_json(
            'Return exactly this JSON object with no extra keys: {"ok": true, "provider_check": "passed"}',
            call_name="debug_llm_call",
        )
    except LLMServiceError as exc:
        print("LLM call failed:")
        print(f"  code: {exc.code}")
        print(f"  provider: {exc.provider or provider}")
        print(f"  model: {exc.model or model}")
        print(f"  status_code: {exc.status_code}")
        print(f"  message: {exc}")
        return 1

    print("LLM call succeeded:")
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
