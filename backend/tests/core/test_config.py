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
