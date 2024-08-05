import asyncio
import logging
import sys
import os
from dotenv import load_dotenv
import tempfile

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, ContentType, FSInputFile

from openai import OpenAI, AssistantEventHandler
from typing_extensions import override
from typing import Optional
from aiofiles import open as aio_open  
from aiohttp import ClientSession

# Загрузка переменных окружения
load_dotenv()

# Проверка на существование необходимых переменных окружения
if not os.getenv('OPENAI_API_KEY') or not os.getenv('TELEGRAM_BOT_TOKEN'):
    raise EnvironmentError("Необходимо установить переменные окружения OPENAI_API_KEY и TELEGRAM_BOT_TOKEN")

# Настройка API
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Создание бота и диспетчера
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Ассистент
assistant = client.beta.assistants.create(
    name="Professional interlocutor",
    instructions="You are a professional interlocutor. You need to answer questions, ask your own and maintain dialogue as much as possible.",
    tools=[{"type": "code_interpreter"}],
    model="gpt-4o",
)

# Поток и буфер для сообщений
thread = client.beta.threads.create()
buffer = []

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)

# Получение файла по ID
async def get_file_path(file_id: str) -> Optional[str]:
    try:
        file_info = await bot.get_file(file_id)
        return file_info.file_path
    except Exception as e:
        logging.error(f"Ошибка при получении пути к файлу: {e}")
        return None

# Скачивание файла во временное хранилище
async def download_file(file_url: str, suffix: str) -> Optional[str]:
    try:
        async with ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    temp_file_path = tempfile.mktemp(suffix=suffix)
                    async with aio_open(temp_file_path, 'wb') as temp_file:
                        await temp_file.write(await response.read())
                    return temp_file_path
                else:
                    logging.error(f"Ошибка при скачивании файла: {response.status}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка при скачивании файла: {e}")
        return None

# Преобразование голоса в текст
async def convert_voice_to_text(file_id: str) -> str:
    try:
        file_path = await get_file_path(file_id)
        if not file_path:
            return "Ошибка при получении пути к файлу."

        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        temp_file_path = await download_file(file_url, ".ogg")
        if not temp_file_path:
            return "Ошибка при скачивании голосового сообщения."
        
        with open(temp_file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        return transcription.text
    except Exception as e:
        logging.error(f"Ошибка при конвертации голосового сообщения в текст: {e}")
        return "Ошибка при конвертации голосового сообщения в текст."
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
         
# Взаимодействие с асистентом  
async def get_ai_response(text: str) -> str:
    try:
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=text
        )

        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant.id,
            instructions="Please address the user as Jane Doe. The user has a premium account.",
            event_handler=EventHandler(),
        ) as stream:
            stream.until_done()
        
        assistants_response = "".join(buffer)
        buffer.clear()
        
        return assistants_response
    except Exception as e:
        logging.error(f"Ошибка при получении ответа от AI: {e}")
        return "Ошибка при получении ответа от AI."

# Конвертация теста в голос
async def convert_text_to_voice(text: str) -> Optional[str]:
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text
        )
        
        temp_file_path = tempfile.mktemp(suffix=".ogg")
        async with aio_open(temp_file_path, 'wb') as temp_file:
            response.stream_to_file(temp_file.name)
    
        return temp_file_path
    except Exception as e:
        logging.error(f"Ошибка при конвертации текста в голос: {e}")
        return None

# Отправка голосового сообщения пользователю
async def send_voice_message(chat_id: int, voice_path: str):
    try:
        voice_file = FSInputFile(voice_path)
        await bot.send_voice(chat_id=chat_id, voice=voice_file)
    except Exception as e:
        logging.error(f"Ошибка при отправке голосового сообщения: {e}")
    finally:
        if os.path.exists(voice_path):
            os.remove(voice_path)

# Класс обработчик событий
class EventHandler(AssistantEventHandler):
    @override
    def on_text_created(self, text) -> None:
        buffer.append(f"\n")
      
    @override
    def on_text_delta(self, delta, snapshot):
        buffer.append(delta.value)
      
    def on_tool_call_created(self, tool_call):
        buffer.append(f"\n{tool_call.type}\n")
  
    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                buffer.append(delta.code_interpreter.input)
            if delta.code_interpreter.outputs:
                buffer.append(f"\n\noutput >")
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        buffer.append(f"\n{output.logs}")

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    try:
        await message.answer(f"Приветствую тебя {message.from_user.first_name}! Давай познакомимся! Можешь задать любой свой вопрос, я тебе помогу!")
    except Exception as e:
        logging.error(f"Ошибка в обработчике команды start: {e}")

# Обработка голосовых сообщений
@dp.message(F.voice)
async def handle_voice_message(message: Message):
    try:
        file_id = message.voice.file_id
        text = await convert_voice_to_text(file_id)
        assistants_response = await get_ai_response(text)
        voice_path = await convert_text_to_voice(assistants_response)
        if voice_path:
            await send_voice_message(message.chat.id, voice_path)
        else:
            await message.answer("Ошибка при конвертации текста в голос.")
    except Exception as e:
        logging.error(f"Ошибка в обработчике голосовых сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения.")

# Обработка текстовых сообщений
@dp.message(F.text)
async def echo_handler(message: Message) -> None:
    try:
        text = message.text
        assistants_response = await get_ai_response(text)
        voice_path = await convert_text_to_voice(assistants_response)
        if voice_path:
            await send_voice_message(message.chat.id, voice_path)
        else:
            await message.answer("Ошибка при конвертации текста в голос.")
    except Exception as e:
        logging.error(f"Ошибка в обработчике голосовых сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения.")

async def main() -> None:
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка в основной функции: {e}")

if __name__ == "__main__":
    asyncio.run(main())
