"""環境變數集中管理。所有設定一律從這裡讀取，禁止在程式碼各處直接呼叫 os.environ。"""

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


app_settings = AppSettings()
