from backend.app.config import Settings


def test_settings_accepts_frontend_backend_url() -> None:
    settings = Settings(backend_url="http://localhost:8000")

    assert settings.backend_url == "http://localhost:8000"


def test_settings_accepts_gemini_model() -> None:
    settings = Settings(gemini_model="gemini-test")

    assert settings.gemini_model == "gemini-test"


def test_settings_accepts_llm_timeout_and_prompt_controls() -> None:
    settings = Settings(
        llm_timeout_seconds=90,
        llm_output_token_limit=1024,
        synthesis_max_claims_per_output=4,
        synthesis_max_evidence_items=12,
    )

    assert settings.llm_timeout_seconds == 90
    assert settings.llm_output_token_limit == 1024
    assert settings.synthesis_max_claims_per_output == 4
    assert settings.synthesis_max_evidence_items == 12


def test_settings_ignores_unrelated_env_file_values() -> None:
    settings = Settings(unused_local_value="ignored")

    assert settings.app_env == "local"
