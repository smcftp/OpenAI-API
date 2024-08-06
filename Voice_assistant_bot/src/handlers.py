import logging
from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from utils import convert_voice_to_text, get_ai_response, convert_text_to_voice, send_voice_message, assistant_initialization

class Form(StatesGroup):
    waiting_for_message = State()

async def command_start_handler(message: Message, state: FSMContext) -> None:
    await message.answer(f"Приветствую тебя {message.from_user.first_name}! Давай познакомимся! Можешь задать любой свой вопрос, я тебе помогу!")
    await state.set_state(Form.waiting_for_message)
    await assistant_initialization()

async def handle_voice_message(message: Message, state: FSMContext):
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

async def handle_text_message(message: Message, state: FSMContext) -> None:
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

def register_handlers1(dp: Dispatcher) -> None:
    dp.message.register(command_start_handler, CommandStart())
    dp.message.register(handle_voice_message, lambda message: message.voice is not None)
    dp.message.register(handle_text_message, lambda message: message.text is not None)
