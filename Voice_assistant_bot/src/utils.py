import logging
import tempfile
import os
from typing import Optional
from aiofiles import open as aio_open
from aiohttp import ClientSession
from aiogram.types import FSInputFile
from openai import AsyncOpenAI, AssistantEventHandler
from typing_extensions import override
from config import set
from config import bot_tg

client = AsyncOpenAI(
    api_key=set.openai_api_key
)

TOKEN = set.telegram_bot_token

buffer = []

# Класс обработчик событий
class EventHandler(AssistantEventHandler):
    @override
    async def on_text_created(self, text) -> None:
        try:
            buffer.append(f"\n{text}")
        except Exception as e:
            logging.error(f"Ошибка в on_text_created: {e}")

    @override
    async def on_text_delta(self, delta, snapshot):
        try:
            buffer.append(delta.value)
        except Exception as e:
            logging.error(f"Ошибка в on_text_delta: {e}")

    @override
    async def on_tool_call_created(self, tool_call):
        try:
            buffer.append(f"\n{tool_call.type}\n")
        except Exception as e:
            logging.error(f"Ошибка в on_tool_call_created: {e}")

    @override
    async def on_tool_call_delta(self, delta, snapshot):
        try:
            print("3")
            if delta.type == 'code_interpreter':
                if delta.code_interpreter.input:
                    buffer.append(delta.code_interpreter.input)
                if delta.code_interpreter.outputs:
                    buffer.append(f"\n\noutput >")
                    for output in delta.code_interpreter.outputs:
                        if output.type == "logs":
                            buffer.append(f"\n{output.logs}")
        except Exception as e:
            logging.error(f"Ошибка в on_tool_call_delta: {e}")

assistant = None
thread = None

# Инициализация ассистента
async def assistant_initialization():
    
    global assistant, thread
    
    # Ассистент
    assistant = await client.beta.assistants.create(
            name="Professional interlocutor",
            instructions="You are a professional interlocutor. You need to answer questions, ask your own and maintain dialogue as much as possible.",
            tools=[{"type": "code_interpreter"}],
            model="gpt-4o",
        )

    thread = await client.beta.threads.create()
    
# Получение файла по ID
async def get_file_path(file_id: str) -> Optional[str]:
    try:
        file_info = await bot_tg.get_file(file_id)
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
            transcription = await client.audio.transcriptions.create(
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

# Взаимодействие с ассистентом  
async def get_ai_response(text: str) -> str:
    try:
        # Создание сообщения пользователя
        message = await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=text
        )

        # Создание и ожидание завершения выполнения
        run = await client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
            instructions="Please address the user as Jane Doe. The user has a premium account."
        )       

        if run.status == 'completed': 
            # Получение списка сообщений
            messages = await client.beta.threads.messages.list(thread_id=thread.id)
            
            # Извлечение значений из сообщений
            assistants_response = [
                message.content[0].text.value 
                for message in messages.data
                if message.content
            ]
        else:
            print(run.status)
        
        # Объединение всех строк в одну
        combined_response = " ".join(assistants_response)
        
        return combined_response
    except Exception as e:
        logging.error(f"Ошибка при получении ответа от AI: {e}")
        return "Ошибка при получении ответа от AI."


# Конвертация теста в голос
async def convert_text_to_voice(text: str) -> Optional[str]:
    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=str(text)
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
        await bot_tg.send_voice(chat_id=chat_id, voice=voice_file)
    except Exception as e:
        logging.error(f"Ошибка при отправке голосового сообщения: {e}")
    finally:
        if os.path.exists(voice_path):
            os.remove(voice_path)
