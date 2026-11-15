from alpaca_bot.config import Settings, read_env_file


def test_env_file_wins_over_environment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# comment\nALPACA_API_KEY="PKFILE"\nexport ALPACA_SECRET_KEY=filesecret\n\n')
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "proxy-injected")
    s = Settings.from_env(f)
    assert (s.api_key, s.secret_key) == ("PKFILE", "filesecret")


def test_falls_back_to_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "envsecret")
    s = Settings.from_env(tmp_path / "missing.env")
    assert (s.api_key, s.secret_key) == ("PKENV", "envsecret")


def test_empty_file_value_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("ALPACA_API_KEY=\n")
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    assert Settings.from_env(f).api_key == "PKENV"
    assert read_env_file(f) == {"ALPACA_API_KEY": ""}
