from alpaca_bot.config import Settings, read_env_file


def test_env_file_wins_over_environment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# comment\nALPACA_API_KEY="PKFILE"\nexport ALPACA_SECRET_KEY=filesecret\n\n',
                 encoding="utf-8")
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "proxy-injected")
    s = Settings.from_env(f, tmp_path / "no-home.env")
    assert (s.api_key, s.secret_key) == ("PKFILE", "filesecret")


def test_home_file_used_when_project_file_missing(tmp_path, monkeypatch):
    home = tmp_path / ".alpaca_bot.env"
    home.write_text("ALPACA_API_KEY=PKHOME\nALPACA_SECRET_KEY=homesecret\n", encoding="utf-8")
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    s = Settings.from_env(tmp_path / "missing.env", home)
    assert (s.api_key, s.secret_key) == ("PKHOME", "homesecret")


def test_falls_back_to_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "envsecret")
    s = Settings.from_env(tmp_path / "missing.env", tmp_path / "missing-home.env")
    assert (s.api_key, s.secret_key) == ("PKENV", "envsecret")


def test_empty_file_value_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("ALPACA_API_KEY=\n", encoding="utf-8")
    monkeypatch.setenv("ALPACA_API_KEY", "PKENV")
    assert Settings.from_env(f, tmp_path / "missing.env").api_key == "PKENV"
    assert read_env_file(f) == {"ALPACA_API_KEY": ""}


def test_windows_notepad_file_with_bom_and_crlf(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"\xef\xbb\xbfALPACA_API_KEY=PKBOM\r\nALPACA_SECRET_KEY=s\r\n")
    assert read_env_file(f) == {"ALPACA_API_KEY": "PKBOM", "ALPACA_SECRET_KEY": "s"}
