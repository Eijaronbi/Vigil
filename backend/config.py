from pathlib import Path

from pydantic_settings import BaseSettings

HERE = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./message_monitor.db"
    telegram_bot_token: str = ""
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    gmail_oauth_refresh_token: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.2-3b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    importance_threshold: int = 6
    digest_interval_minutes: int = 30
    daily_report_time: str = "08:00"
    ws_port: int = 8765
    monad_rpc_url: str = "https://mainnet-rpc.monad.xyz"
    monad_explorer_url: str = "https://monadscan.com"
    monad_chain_id: int = 143
    contract_address: str = ""
    wallet_private_key: str = ""
    auth_password: str = "vigil"
    jina_api_key: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@vigil-monitor.app"

    model_config = {"env_file": HERE / ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
