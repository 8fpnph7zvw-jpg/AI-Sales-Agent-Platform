from app.core.config import Settings


def test_cors_origins_accepts_comma_separated_environment_value(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://sales.example.com, https://admin.example.com",
    )

    settings = Settings()

    assert settings.cors_origins == [
        "https://sales.example.com",
        "https://admin.example.com",
    ]


def test_openwa_defaults_use_docker_service_dns() -> None:
    settings = Settings(_env_file=None)

    assert settings.openwa_url == "http://openwa:2785/api"
    assert settings.openwa_session == "ai-sales-agent"
