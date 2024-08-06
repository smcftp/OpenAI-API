from pydantic_settings import BaseSettings
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

class Settings(BaseSettings):
    openai_api_key: str
    telegram_bot_token: str

    class Config:
        env_file = 'D:\Programming\Python\GPT\Voice_AI_bot_on_Aiogram\Voice_assistant_bot\.env'

set = Settings()

bot_tg = Bot(token=set.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

