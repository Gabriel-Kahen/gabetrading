from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Live Paper Trading Backend"
    starting_capital: float = 100_000.0
    trading_interval_seconds: int = 60
    market_closed_poll_seconds: int = 300
    news_refresh_seconds: int = 300
    daily_history_refresh_seconds: int = 1800
    universe_refresh_seconds: int = 43200
    universe_limit: int = Field(default=500, ge=25, le=500)
    lookback_days: int = 90
    intraday_lookback_days: int = Field(default=10, ge=5, le=60)
    intraday_interval: str = "15m"
    max_longs: int = 12
    max_shorts: int = 8
    max_position_weight: float = 0.12
    gross_exposure_limit: float = 1.25
    long_score_threshold: float = 0.15
    short_score_threshold: float = -0.15
    min_rebalance_notional: float = 15_000.0
    min_rebalance_weight_change: float = 0.01
    auto_run_on_start: bool = True
    data_dir: Path = Path("data")
    state_file_name: str = "state.json"
    database_file_name: str = "state.sqlite3"
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_base_url: str | None = None
    enable_trade_explanations: bool = True
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    discord_webhook_url: str | None = None
    alert_cooldown_seconds: int = 900
    anomaly_return_threshold_pct: float = 5.0
    anomaly_duration_minutes: int = 60

    @property
    def state_file(self) -> Path:
        return self.data_dir / self.state_file_name

    @property
    def database_file(self) -> Path:
        return self.data_dir / self.database_file_name


settings = Settings()
