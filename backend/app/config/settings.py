"""環境變數集中管理。所有設定一律從這裡讀取，禁止在程式碼各處直接呼叫 os.environ。"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 本機 docker-compose 的預設值，讓 `pip install` 後不需要先手動建立 .env
    # 也能直接跑起來；雲端環境一律由平台的環境變數覆蓋。
    # 用 5442/5443 而非預設的 5432/5433，因為舊專案 employee-portal 的
    # docker-compose 佔用了那兩個 port（見 docker-compose.yml 的註解）。
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5442/employee_portal"
    TEST_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5443/employee_portal_test"

    JWT_SECRET: str = "dev-only-insecure-secret-change-in-production"
    JWT_EXPIRES_IN_HOURS: int = 24

    APP_TIMEZONE: str = "Asia/Taipei"
    CORS_ORIGINS: str = "http://localhost:5173"

    # 正式環境才啟動閒置自動重置排程；設為 0 可關閉。
    DEMO_RESET_IDLE_MINUTES: int = 15

    PORT: int = 3000
    ENVIRONMENT: str = "development"

    # AI 政策問答（批 A）。留空即視為未啟用——GOOGLE_API_KEY 是唯一的啟用開關，
    # 見 chat_enabled property 與 openspec/changes/add-policy-chat/design.md。
    GOOGLE_API_KEY: str = ""
    # 實測 gemini-3.5-flash-lite 的延遲抖動極大（同一支程式、同一組輸入量到
    # 1.5～52.7 秒，還會直接逾時），gemini-3.1-flash-lite 則穩定在 2～9 秒，
    # 品質經 77 題 eval 驗證無退步，因此選它（見 docs/PITFALLS.md I11）。
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    # 只作用在批次作業（ingest／eval）；互動式問答刻意不節流，配額保護交給
    # CHAT_RATE_LIMIT_PER_MINUTE（明確回 429 遠比默默拖慢每次回答誠實）。
    GEMINI_REQUESTS_PER_MINUTE: float = 10
    # 換掉抖動的模型之後，實測落在 2～9 秒，40 秒是留給偶發長尾的餘裕。
    GEMINI_TIMEOUT_SECONDS: float = 40
    # 影響用詞隨機性，不是「語氣溫暖度」。調整必須重跑 eval，見 utils/gemini.py。
    GEMINI_TEMPERATURE: float = 0.3
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIM: int = 768
    RETRIEVAL_TOP_K: int = 5
    # 綁死在「這個模型 + 768 維 + 兩側 L2 正規化 + 不對稱 task_type」這一整組設定上，
    # 任一項變動即作廢，須重跑 backend/eval/measure_min_score.py 重新校準。
    RETRIEVAL_MIN_SCORE: float = 0.65
    CHAT_RATE_LIMIT_PER_MINUTE: int = 10
    CHAT_MAX_QUESTION_CHARS: int = 500

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def chat_enabled(self) -> bool:
        return bool(self.GOOGLE_API_KEY.strip())

    @model_validator(mode="after")
    def _forbid_open_cors_in_production(self) -> "AppSettings":
        # 開放 CORS 的正式環境等於任何網站都能代替使用者打這組 API；寧可讓服務
        # 啟動失敗，也不要放行一個沒設定明確白名單的正式環境（README.md 雲端部署章節）。
        if self.ENVIRONMENT == "production" and (not self.CORS_ORIGINS.strip() or self.CORS_ORIGINS.strip() == "*"):
            raise ValueError("正式環境（ENVIRONMENT=production）必須設定明確的 CORS_ORIGINS，不得留空或設為 *")
        return self


app_settings = AppSettings()
