from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./message_monitor.db"
    telegram_bot_token: str = ""
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    gmail_oauth_refresh_token: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    importance_threshold: int = 6
    digest_interval_minutes: int = 30
    daily_report_time: str = "08:00"
    ws_port: int = 8765
    monad_rpc_url: str = "https://testnet-rpc.monad.xyz"
    contract_address: str = ""
    wallet_private_key: str = ""
    auth_password: str = "vigil"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
