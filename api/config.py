from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # MongoDB
    mongo_uri: str = ""
    mongo_db: str = "waf_db"
    mongo_collection: str = "analysis_logs"

    # Model paths
    model_path: str = "./model/checkpoints/distilbert_http_mlm_epoch22"
    scaler_path: str = "scaler.pkl"
    iforest_path: str = "iforest.pkl"
    train_features_path: str = "train_features_dvwa_fix_seed.npy"

    # Inference
    max_length: int = 256
    num_inference_runs: int = 5
    mask_prob: float = 0.15
    z_score_threshold: float = 7.0

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
