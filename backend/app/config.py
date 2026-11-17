"""환경변수 설정. 비밀값은 여기(서버 환경변수)에만 두고, 브라우저로 내려보내거나 로그에 남기지 않는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 앱
    app_env: Literal["dev", "prod"] = Field("dev", validation_alias=AliasChoices("AP_ENV", "APP_ENV"))
    data_dir: Path = Field(Path("./data"), validation_alias="AP_DATA_DIR")
    allowed_hosts: str = Field("localhost,127.0.0.1", validation_alias="AP_ALLOWED_HOSTS")
    public_origin: str = Field("", validation_alias="AP_PUBLIC_ORIGIN")
    static_dir: Path | None = Field(None, validation_alias="AP_STATIC_DIR")
    # 보안: 운영(prod)에서는 둘 다 반드시 환경변수로 넣는다.
    secret_key: SecretStr = Field(SecretStr(""), validation_alias="AP_SECRET_KEY")  # TOTP 비밀값 암호화 키의 재료
    setup_token: SecretStr = Field(SecretStr(""), validation_alias="AP_SETUP_TOKEN")  # 최초 관리자 등록에 필요한 1회용 값

    # 운영
    backup_keep: int = Field(14, ge=0, le=365, validation_alias="AP_BACKUP_KEEP")  # 하루 한 번 자동 백업을 몇 개 남길지(0이면 끔)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", validation_alias="AP_LOG_LEVEL")

    # 데이터
    data_provider: Literal["naver", "sample"] = Field("naver", validation_alias="AP_DATA_PROVIDER")

    # 실전 매매 잠금: 이 값이 참이 아니면 실전 전환 자체가 불가능하다.
    allow_live_trading: bool = Field(False, validation_alias="ALLOW_LIVE_TRADING")

    # 키움 REST (환경별로 키가 다르다)
    kiwoom_mock_app_key: SecretStr = Field(SecretStr(""), validation_alias="KIWOOM_MOCK_APP_KEY")
    kiwoom_mock_secret_key: SecretStr = Field(SecretStr(""), validation_alias="KIWOOM_MOCK_SECRET_KEY")
    kiwoom_live_app_key: SecretStr = Field(SecretStr(""), validation_alias="KIWOOM_LIVE_APP_KEY")
    kiwoom_live_secret_key: SecretStr = Field(SecretStr(""), validation_alias="KIWOOM_LIVE_SECRET_KEY")

    # Claude API
    anthropic_api_key: SecretStr = Field(SecretStr(""), validation_alias="ANTHROPIC_API_KEY")

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "alphapilot.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "engine.lock"

    @property
    def host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    def production_problems(self) -> list[str]:
        """운영(prod)으로 띄우기 전에 고쳐야 할 설정. 비어 있으면 띄워도 된다."""
        problems: list[str] = []
        if len(self.secret_key.get_secret_value()) < 32:
            problems.append("AP_SECRET_KEY가 비었거나 너무 짧습니다(32자 이상, .env.example의 만들기 명령 참고)")
        if not self.host_list or all(h in {"localhost", "127.0.0.1", "::1"} for h in self.host_list):
            problems.append("AP_ALLOWED_HOSTS에 접속할 실제 도메인을 넣으세요")
        if self.data_provider == "sample":
            problems.append("AP_DATA_PROVIDER=sample(가짜 데이터)로는 운영하지 않습니다")
        if self.allow_live_trading and not self.has_kiwoom_keys("live"):
            problems.append("ALLOW_LIVE_TRADING=true인데 키움 실전 키가 없습니다")
        return problems

    def kiwoom_keys(self, env: Literal["mock", "live"]) -> tuple[str, str]:
        if env == "mock":
            return (self.kiwoom_mock_app_key.get_secret_value(), self.kiwoom_mock_secret_key.get_secret_value())
        return (self.kiwoom_live_app_key.get_secret_value(), self.kiwoom_live_secret_key.get_secret_value())

    def has_kiwoom_keys(self, env: Literal["mock", "live"]) -> bool:
        app_key, secret = self.kiwoom_keys(env)
        return bool(app_key and secret)

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
