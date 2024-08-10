import logging
import tempfile
import os
import json
from typing import Optional

from aiofiles import open as aio_open
from aiohttp import ClientSession
from aiogram.types import FSInputFile

from openai import AsyncOpenAI

from amplitude import Amplitude, BaseEvent

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from typing_extensions import override

from config import set, bot_tg, thread, assistant, executor
from src.models import User, UserValue
from src.database import SessionLocal, engine, Base

client = AsyncOpenAI(
    api_key=set.openai_api_key
)

TOKEN = set.telegram_bot_token

amp_client = Amplitude(api_key=set.amplitude_api_key)
    
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
async def get_ai_response(text: str, user_id) -> str:
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
        print(run.status)    

        if run.status == 'requires_action': 
            # Define the list to store tool outputs
            tool_outputs = []
            
            # Loop through each tool in the required action section
            for tool in run.required_action.submit_tool_outputs.tool_calls:
                if tool.function.name == "save_value":
                    print("Ценность определена")
                    # Получение данных из ответа функции
                    try:
                        json_string = str(tool.function)
                        start_index = json_string.find('{')
                        end_index = json_string.rfind('}')
                        if start_index != -1 and end_index != -1 and end_index > start_index:
                            extracted_text = json_string[start_index + 1:end_index]
                        json_data = json.loads('{' + extracted_text + '}')
                        opinions = json_data['opinions']
                        values = json_data['values']
                        
                        # Сохранение ценности в БД
                        validation_result = await validate_value(opinions)
                        telegram_id = str(user_id)
                        if validation_result == True:
                            print("Ценность подтверждена")
                            
                            # Отправка сообщения в amplitude
                            event_type = "ValueAnalysis"
                            event = {
                                "keywords": ["value", "analysis"],
                                "likes": True
                            }
                            
                            # Закоменчено так как бот работает только с VPN, а БД не поддерживает
                            # Сохранение значений в БД
                            # await create_tables()
                            # Пример добавления данных
                            # await add_user_value(telegram_id, values)
                        
                    except json.JSONDecodeError as e:
                        print(f"Error decoding function date: {e}")

                    except KeyError as e:
                        print(f"KeyError: {e}. Function date does not contain expected keys.")
                
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": "Хорошо я запомнил ваше предпочтение, что это ваша ценность."
                }) 
                
                # Submit all tool outputs at once after collecting them in a list
                if tool_outputs:
                    try:
                        run = await client.beta.threads.runs.submit_tool_outputs_and_poll(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=tool_outputs
                        )
                        print("Tool outputs submitted successfully.")
                    except Exception as e:
                        print("Failed to submit tool outputs:", e)
                else:
                    print("No tool outputs to submit.")
                
                if run.status == 'completed':
                    messages = await client.beta.threads.messages.list(
                        thread_id=thread.id
                    )
                    # assistants_response = messages.data[0].content[0].text.value
                    assistants_response = messages.data[0].content[0].text
                    
                    annotations = assistants_response.annotations
                    citations = []
                    for index, annotation in enumerate(annotations):
                        assistants_response.value = assistants_response.value.replace(annotation.text, f"[{index}]")
                        if file_citation := getattr(annotation, "file_citation", None):
                            cited_file = await client.files.retrieve(file_citation.file_id)
                            citations.append(f"[{index}] {cited_file.filename}")
                    combined_output = f"{assistants_response.value}\n\n" + "\n".join(citations)
                    return combined_output
                else:
                    print(run.status)
                    
        elif run.status == 'completed':   
            # Получение списка сообщений
            messages = await client.beta.threads.messages.list(thread_id=thread.id)
            # assistants_response = messages.data[0].content[0].text.value
            assistants_response = messages.data[0].content[0].text
            
            annotations = assistants_response.annotations
            citations = []
            for index, annotation in enumerate(annotations):
                assistants_response.value = assistants_response.value.replace(annotation.text, f"[{index}]")
                if file_citation := getattr(annotation, "file_citation", None):
                    cited_file = await client.files.retrieve(file_citation.file_id)
                    citations.append(f"[{index}] {cited_file.filename}")
            combined_output = f"{assistants_response.value}\n\n" + "\n".join(citations)
            return combined_output
        else:
            raise Exception("Run status is not 'completed' and requires further investigation.")
            
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

# Проверка ценности
async def validate_value(value: str) -> bool:
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_delivery_date",
                "description": "Сhecking user expression. Сhecking if the expression contains a user their personal opinion or values important.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "proof_of_value": {
                            "type": "boolean",
                            "description": "True if it contain personal opinion or important values and False if it is not",
                        },
                    },
                    "required": ["proof_of_value"],
                    "additionalProperties": False,
                },
            }
        }
    ]
    
    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages = [
            {"role": "system", "content": "You are a helpful customer support assistant. Use the supplied tools to assist the user."},
            {"role": "user", "content": "{}".format(value)}
        ],
        tools=tools,
    )
    
    if completion.choices[0].finish_reason == 'stop':
        return False
    elif completion.choices[0].finish_reason == 'tool_calls':
        print(completion)
        return bool(json.loads(completion.choices[0].message.tool_calls[0].function.arguments)["proof_of_value"])

# Сохранение ценности в БД 
# Пример создания таблиц в базе данных
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Добавление ценности
async def add_user_value(telegram_id, value):
    try:
        async with SessionLocal() as session:
            async with session.begin():
                existing_record = await session.execute(
                    select(UserValue).where(UserValue.telegram_id == telegram_id)
                )
                if existing_record.scalars().first():
                    print(f"Record with telegram_id {telegram_id} already exists.")
                else:
                    new_value = UserValue(telegram_id=telegram_id, value=value)
                    session.add(new_value)
                    try:
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        print(f"Could not insert {telegram_id}: {value}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении ценности для telegram_id={telegram_id}: {str(e)}")
        raise

# Aнализ эмоций на полученом фото
async def analyze_photo(file_path):
    photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
            "role": "user",
            "content": [
                {"type": "text", "text": "You need to determine whether there is a human face in the photo. If there is, then determine the emotions that the person is experiencing; if there is no face or it is impossible to determine the emotions, return only word False."},
                {
                "type": "image_url",
                "image_url": {
                    "url": photo_url,
                },
                },
            ],
            }
        ],
        max_tokens=300,
    )
    
    return response.choices[0].message.content

# Функция для отправки событий в Amplitude
def send_event_to_amplitude(user_id, chat_id, event_type, event_properties):
    try:
        # Create a BaseEvent instance
        event = BaseEvent(event_type=event_type, user_id=user_id, device_id=chat_id)
        
        # # Set event properties if provided
        # if event_properties:
        #     event["event_properties"] = event_properties
        
        # Отправляем событие в Amplitude
        amp_client.track(event)
        print(f"Событие типа '{event_type}' для пользователя {user_id} отправлено в Amplitude")
    except Exception as e:
        print(f"Ошибка при отправке события в Amplitude: {e}")
