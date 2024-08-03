import requests
import pandas as pd
from datetime import datetime, timedelta
import openai

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка API
# Получение ключей из переменных окружения
openai.api_key = os.getenv('OPENAI_API_KEY')
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')

class CryptoAnalyzer:
    def __init__(self, openai_key, news_api_key):
        # Инициализация ключей API
        self.openai_key = openai_key
        self.news_api_key = news_api_key
        openai.api_key = openai_key

    # Получение цен криптовалюты
    def get_crypto_prices(self, crypto_id='bitcoin', days=2):
        url = f'https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart'
        params = {
            'vs_currency': 'usd',
            'days': days
        }
        response = requests.get(url, params=params)
        data = response.json()
    
        # Создание DataFrame из данных цен
        prices = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
    
        # Получение первого и последнего значения из второго столбца
        second_column = prices.iloc[:, 1]  # Второй столбец (индекс 1)
    
        present_value = int(second_column.iloc[-1])  # Текущая цена
        past_value = int(second_column.iloc[0])  # Цена в начале периода
    
        return present_value, past_value

    # Получение новостей
    def get_crypto_news(self, query='bitcoin', days=7):
        api_key = self.news_api_key  # Используем ключ из переменных окружения
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        url = 'https://newsapi.org/v2/everything'
        params = {
           'q': query,
            'from': start_date.isoformat(),
           'to': end_date.isoformat(),
           'sortBy': 'relevancy',
           'language': 'en',
           'apiKey': api_key
        }
        response = requests.get(url, params=params)
        data = response.json()
    
        # Получение списка статей
        articles = data['articles']
        return articles

    # Анализ новостей с помощью GPT-4
    
    def analyze_news_with_gpt4(self, news_articles):
        # Create a list of headlines from news articles
        headlines = [article['title'] for article in news_articles]

        # Construct the prompt for GPT-4
        prompt = "Analyze the sentiment of the following news headlines and provide the sentiment for each Positive (1), Neutral(0), Negative(-1): \n\n"
        for i, headline in enumerate(headlines, 1):
            prompt += f"{i}. \"{headline}\"\n"

        # prompt += "\nIn your answer, return only the number corresponding to the sentiment of the news for each headline, in the same order. That is, in the form of a table like the name of the news in the column is only sentiment number."
        
        prompt += "\nIn your answer, return ONLY a column of NUMBERS (just numbers) corresponding to the sentiment"

        results = []

        try:
            # Call OpenAI API to analyze sentiments
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )

            # Parse sentiment analysis results
            sentiment_analysis = response['choices'][0]['message']['content'].strip().split("\n")

            # Ensure lengths match before iterating
            # if len(headlines) != len(sentiment_analysis):
            #     raise ValueError("Number of headlines does not match number of sentiment analyses")

            # Create results dictionary
            results = []
            for i, sentiment in enumerate(sentiment_analysis):
                results.append({
                    'title': headlines[i],
                    'analysis': sentiment
                })

        except openai.error.PermissionError as e:
            print(f"OpenAI PermissionError: {e}")
        except Exception as e:
            print(f"Error analyzing news with GPT-4: {e}")

        return results

    # Анализ сообщений пользователя
    def analyze_user_message(self, message):
        
        # Получение текущей даты
        current_date = datetime.now().date()
        
        # Запрос для анализа сообщения пользователя
        prompt = f"""Analyze the sentiment of the following user message and provide the corresponding number:
            Return -1 if the message is a question about the functionality of this Telegram bot.
            Return the number of the day the user is asking about in his massage only then If the message is a question about how much the price of Bitcoin has changed over a certain period of time exactly in the past (if the question includes a date in any format, calculate the value of this interval in days from current date = \"{current_date}\"), .
            In all other cases, return -2.
            Message: \"{message}\"
            In your answer, return only the number corresponding to the sentiment of the message."""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.7
            )

            # Обработка результата анализа сообщения
            result = response['choices'][0]['message']['content'].strip()
    
            return result
        except ValueError:
            return -4
        except openai.error.PermissionError as e:
            print(f"OpenAI PermissionError: {e}")

    # Формирование окончательного сообщения
    def formation_final_message(self, days):
    
        # Получение списка новостей
        news = self.get_crypto_news(query='bitcoin', days=days)
        
        # Получение разбитого по сантиментам списка нвостей
        analyzed_news = self.analyze_news_with_gpt4(news)
        print(analyzed_news)
        
        # Почучение информации о изменении цены
        present_value, past_value = self.get_crypto_prices(crypto_id='bitcoin', days=days)

        # Определение направления изменения цены
        direction = present_value > past_value
        direction_word = 'increased' if direction else 'decreased'

        check = '1' if direction else '-1'
        
        # Формирование текста новостей на основе анализа сентимента
        news_text = ""
        for analysis in analyzed_news:
            if analysis['analysis'] == check:
                news_text += f"- {analysis['title']}\n"
        percentage_change = round(abs(((present_value - past_value) / past_value) * 100), 2)

        return f"Bitcoin price for a period of {days} days {direction_word} by {percentage_change}%. \n\nThis is due to the following news events over the given period:\n{news_text}"

# Создание экземпляра класса CryptoAnalyzer
crypto_analyzer = CryptoAnalyzer(openai_key=openai.api_key, news_api_key=NEWS_API_KEY)

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    # Обработка команды /start
    await message.answer("Hello! I am your Telegram bot for cryptocurrency analysis and news.")

@dp.message()
async def echo_handler(message: Message) -> None:
    last_user_message = message.text
    # Анализ сообщения пользователя
    analysis_result = crypto_analyzer.analyze_user_message(last_user_message)
    print(analysis_result)
    
    if analysis_result == '-1':
        # Ответ на запрос о функционале бота
        await message.answer("I can help you find out the current prices of cryptocurrencies, get the latest news about them, and analyze these news.")
    elif analysis_result == '-2':
        # Ответ на запрос о нефункциональных возможностях
        await message.answer("Sorry, I don't have this functionality.")
    else:
        days = int(analysis_result)
        if days is None or not isinstance(days, int):
            logging.error(f"Invalid value for days: {days}")
            await message.answer("Sorry, there was an error processing your request.")
            return
        finally_message = crypto_analyzer.formation_final_message(days)
        await message.answer(finally_message)

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Настройка уровня логирования и запуск основного цикла событий
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
