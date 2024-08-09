import logging

from aiogram import Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from utils import convert_voice_to_text, get_ai_response, convert_text_to_voice, send_voice_message, analyze_photo, send_event_to_amplitude
from config import bot_tg, set, executor

dp = Dispatcher()

class Form(StatesGroup):
    waiting_for_message = State()

@dp.message(Command('start'))
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await message.answer(f"Приветствую тебя {message.from_user.first_name}!\nДавай познакомимся! Можешь задать любой свой вопрос, я тебе помогу! \nЯ могу:\n1) Общаться на любую тему на разных языках. \n2) Принимать голосовые и текстовые сообщения. \n3) Анализировать по фото, какие эмоции испытывает человек.")
    await state.set_state(Form.waiting_for_message)
    # await assistant_initialization()

# Обработка голосовых сообщений
@dp.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    try:
        # Отправка сообщения в amplitude
        user_id =str(message.from_user.id)
        chat_id = str(message.chat.id)
        event_type = "VoiseMessage"
        event = {
            "keywords": ["voise", "message"],
            "likes": True
        }
        executor.submit(send_event_to_amplitude, user_id, chat_id, event_type, event)
        
        file_id = message.voice.file_id
        text = await convert_voice_to_text(file_id)
        assistants_response = await get_ai_response(text, user_id, chat_id)
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
async def handle_text_message(message: Message, state: FSMContext) -> None:
    try:
        # Отправка сообщения в amplitude
        user_id = str(message.from_user.id)
        chat_id = str(message.chat.id)
        event_type = "TextMessage"
        event = {
            "keywords": ["text", "message"],
            "likes": True
        }
        executor.submit(send_event_to_amplitude, user_id, chat_id, event_type, event)
        
        text = message.text
        assistants_response = await get_ai_response(text, user_id, chat_id)
        # await message.answer(assistants_response)
        voice_path = await convert_text_to_voice(assistants_response)
        if voice_path:
            await send_voice_message(message.chat.id, voice_path)
        else:
            await message.answer("Ошибка при конвертации текста в голос.")
    except Exception as e:
        logging.error(f"Ошибка в обработчике голосовых сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения.")
        
# Обработка присланых изображений
@dp.message(F.photo)
async def handle_image_message(message: Message, state: FSMContext) -> None:
    try:
        # Отправка сообщения в amplitude
        user_id = str(message.from_user.id)
        chat_id = str(message.chat.id)
        event_type = "PhotoAnalyzed"
        event = {
            "keywords": ["emotion", "photo", "image", "analyses"],
            "likes": True
        }
        executor.submit(send_event_to_amplitude, user_id, chat_id, event_type, event)
        
        # Анализ фото
        file_id = message.photo[-1].file_id
        file_info = await bot_tg.get_file(file_id)
        file_path = file_info.file_path
        
        photo_analysis_result = await analyze_photo(file_path)
        
        if photo_analysis_result == 'False':
            text = 'На фото нельзя определить человеские эмоции.'
            voice_path = await convert_text_to_voice(text)
            if voice_path:
                await send_voice_message(message.chat.id, voice_path)
            else:
                await message.answer("Ошибка при конвертации текста в голос.")
        else:
            text = photo_analysis_result
            voice_path = await convert_text_to_voice(text)
            if voice_path:
                await send_voice_message(message.chat.id, voice_path)
            else:
                await message.answer("Ошибка при конвертации текста в голос.")
        
    except Exception as e:
        logging.error(f"Ошибка в обработчике голосовых сообщений: {e}")
        await message.answer("Произошла ошибка при обработке вашего сообщения.")

def register_handlers1(dp: Dispatcher) -> None:
    dp.message.register(command_start_handler, CommandStart())
    dp.message.register(handle_voice_message, lambda message: message.voice is not None)
    dp.message.register(handle_text_message, lambda message: message.text is not None)
    dp.message.register(handle_image_message, lambda message: message.photo is not None)
