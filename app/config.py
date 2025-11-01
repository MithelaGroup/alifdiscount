from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "ALIF Discount"
    APP_BASE_URL: str = "https://dsc.alif.clothing"
    SECRET_KEY: str = "CHANGE_ME"
    SESSION_COOKIE_NAME: str = "alif_session"
    ENV: str = "production"

    # Database
    DATABASE_URL: str = "sqlite:///./data.db"

    # SMTP (Microsoft 365 STARTTLS)
    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@example.com"

    # WhatsApp Business Cloud
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_TEMPLATE_TEXT: str = (
        "Dear {name}, your discount {discount}% has been approved.\n"
        "Coupon: {coupon}\n"
        "Ref: {request_code}\n"
        "Thank you."
    )

    # Web Push (optional)
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:admin@example.com"

settings = Settings()
