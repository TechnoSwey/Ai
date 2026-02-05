import os
import json
import logging
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PROXYAPI_KEY = os.getenv('PROXYAPI_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')

PROXYAPI_BASE_URL = "https://api.proxyapi.ru"

class AIModel(Enum):
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

@dataclass
class ModelConfig:
    name: str
    endpoint: str
    model_name: str
    provider: str
    headers: Dict

class UserDB:
    def __init__(self):
        self.users_file = "users.json"
        self.load_users()
    
    def load_users(self):
        try:
            with open(self.users_file, 'r') as f:
                self.users = json.load(f)
        except:
            self.users = {}
    
    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def get_user(self, user_id: int):
        if str(user_id) not in self.users:
            self.users[str(user_id)] = {
                "requests_left": 0,
                "total_requests": 0,
                "selected_model": "chatgpt"
            }
            self.save_users()
        return self.users[str(user_id)]
    
    def update_user(self, user_id: int, data: dict):
        user = self.get_user(user_id)
        user.update(data)
        self.save_users()
    
    def add_requests(self, user_id: int, amount: int):
        user = self.get_user(user_id)
        user["requests_left"] = user.get("requests_left", 0) + amount
        self.save_users()

user_db = UserDB()

class ProxyAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = PROXYAPI_BASE_URL
        
        self.configs = {
            AIModel.CHATGPT: ModelConfig(
                name="ChatGPT",
                endpoint="/openai/v1/chat/completions",
                model_name="gpt-4-turbo-preview",
                provider="openai",
                headers={"Authorization": f"Bearer {api_key}"}
            ),
            AIModel.CLAUDE: ModelConfig(
                name="Claude 3",
                endpoint="/anthropic/v1/messages",
                model_name="claude-3-haiku-20240307",
                provider="anthropic",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
            ),
            AIModel.GEMINI: ModelConfig(
                name="Gemini Pro",
                endpoint="/google/v1/models/gemini-pro:generateContent",
                model_name="gemini-pro",
                provider="google",
                headers={"Authorization": f"Bearer {api_key}"}
            ),
            AIModel.DEEPSEEK: ModelConfig(
                name="DeepSeek",
                endpoint="/openai/v1/chat/completions",
                model_name="deepseek-chat",
                provider="deepseek",
                headers={"Authorization": f"Bearer {api_key}"}
            )
        }
    
    async def send_request(self, user_id: int, prompt: str) -> Optional[str]:
        user = user_db.get_user(user_id)
        model_name = user["selected_model"]
        
        model_map = {
            "chatgpt": AIModel.CHATGPT,
            "claude": AIModel.CLAUDE,
            "gemini": AIModel.GEMINI,
            "deepseek": AIModel.DEEPSEEK
        }
        
        model = model_map.get(model_name, AIModel.CHATGPT)
        config = self.configs[model]
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}{config.endpoint}"
                
                if model == AIModel.CHATGPT:
                    payload = {
                        "model": config.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000
                    }
                    
                    async with session.post(url, json=payload, headers=config.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data['choices'][0]['message']['content']
                
                elif model == AIModel.CLAUDE:
                    payload = {
                        "model": config.model_name,
                        "max_tokens": 2000,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                    
                    async with session.post(url, json=payload, headers=config.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data['content'][0]['text']
                
                elif model == AIModel.GEMINI:
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}]
                    }
                    
                    async with session.post(url, json=payload, headers=config.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data['candidates'][0]['content']['parts'][0]['text']
                
                elif model == AIModel.DEEPSEEK:
                    payload = {
                        "model": config.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000
                    }
                    
                    async with session.post(url, json=payload, headers=config.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data['choices'][0]['message']['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

ai_client = ProxyAPIClient(PROXYAPI_KEY)

async def create_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, package_type: str):
    user_id = update.effective_user.id
    
    packages = {
        "1": {"requests": 1, "price": 5, "description": "1 запрос к AI"},
        "5": {"requests": 5, "price": 25, "description": "5 запросов к AI"},
        "10": {"requests": 11, "price": 50, "description": "10+1 запросов к AI"},
        "100": {"requests": 105, "price": 500, "description": "100+5 запросов к AI"}
    }
    
    if package_type not in packages:
        return
    
    package = packages[package_type]
    
    payload = {
        "chat_id": user_id,
        "title": f"Пакет {package_type} запросов",
        "description": package["description"],
        "payload": f"package_{package_type}_{user_id}",
        "provider_token": "", 
        "currency": "XTR",
        "prices": [{"label": "Запросы к AI", "amount": package["price"]}],
        "max_tip_amount": 0,
        "suggested_tip_amounts": [],
        "start_parameter": "ai_requests",
        "photo_url": "https://img.icons8.com/color/96/000000/artificial-intelligence.png",
        "need_name": False,
        "need_phone_number": False,
        "need_email": False,
        "need_shipping_address": False,
        "send_phone_number_to_provider": False,
        "send_email_to_provider": False,
        "is_flexible": False
    }
    
    try:
        await context.bot.send_invoice(**payload)
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await update.callback_query.message.reply_text(
            "❌ Ошибка при создании счета. Пожалуйста, попробуйте позже."
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = user_db.get_user(user.id)
    
    text = f"""🤖 *Добро пожаловать, {user.first_name}!*

📊 *Ваш баланс:* {user_data['requests_left']} запросов

💎 *Тарифы:*
• 1 запрос = 5⭐
• 5 запросов = 25⭐
• 10 запросов = 50⭐ (+1 бонусный)
• 100 запросов = 500⭐ (+5 бонусных)

🤖 *Доступные модели:*
• ChatGPT (GPT-4 Turbo)
• Claude 3 (Haiku)
• Gemini Pro
• DeepSeek Chat

📋 *Команды:*
/model - Выбрать модель
/balance - Баланс
/buy - Купить запросы
/help - Помощь"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Выбрать модель", callback_data='select_model')],
        [InlineKeyboardButton("💰 Баланс", callback_data='balance')],
        [InlineKeyboardButton("🛒 Купить запросы", callback_data='buy')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_model_selection(update, context)

async def show_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_db.get_user(update.effective_user.id)
    current_model = user["selected_model"]
    
    model_display = {
        "chatgpt": "🤖 ChatGPT",
        "claude": "🧠 Claude 3",
        "gemini": "⭐ Gemini Pro",
        "deepseek": "🚀 DeepSeek"
    }
    
    keyboard = [
        [InlineKeyboardButton(f"{model_display['chatgpt']} ✅" if current_model == "chatgpt" else model_display['chatgpt'], callback_data='set_chatgpt')],
        [InlineKeyboardButton(f"{model_display['claude']} ✅" if current_model == "claude" else model_display['claude'], callback_data='set_claude')],
        [InlineKeyboardButton(f"{model_display['gemini']} ✅" if current_model == "gemini" else model_display['gemini'], callback_data='set_gemini')],
        [InlineKeyboardButton(f"{model_display['deepseek']} ✅" if current_model == "deepseek" else model_display['deepseek'], callback_data='set_deepseek')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"*Выберите модель:*\nТекущая: {model_display[current_model]}"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_db.get_user(update.effective_user.id)
    
    text = f"""💰 *Ваш баланс*

📊 *Доступно запросов:* {user['requests_left']}
📈 *Всего использовано:* {user['total_requests']}

💎 *Цены:*
• 1 запрос = 5⭐
• 5 запросов = 25⭐
• 10 запросов = 50⭐ (+1 бонус)
• 100 запросов = 500⭐ (+5 бонусов)

💳 *Оплата через Telegram Stars*
Используйте /buy для покупки"""
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить запросы", callback_data='buy')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🛒 *Купить запросы*

💎 *Выберите пакет:*

1️⃣ *1 запрос* = 5⭐
• 1 запрос к любой модели

5️⃣ *5 запросов* = 25⭐
• 5 запросов к любой модели

🔟 *10 запросов* = 50⭐
• 10 запросов + 1 бонусный = 11 запросов

💯 *100 запросов* = 500⭐
• 100 запросов + 5 бонусных = 105 запросов

💳 *Оплата Telegram Stars*
Нажмите на кнопку для создания счета"""
    
    keyboard = [
        [
            InlineKeyboardButton("1 запрос (5⭐)", callback_data='invoice_1'),
            InlineKeyboardButton("5 запросов (25⭐)", callback_data='invoice_5')
        ],
        [
            InlineKeyboardButton("10 запросов (50⭐)", callback_data='invoice_10'),
            InlineKeyboardButton("100 запросов (500⭐)", callback_data='invoice_100')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """❓ *Помощь*

🤖 *Как использовать:*
1. Купите запросы через /buy
2. Выберите модель командой /model
3. Отправьте свой запрос боту
4. Получите ответ от AI

💰 *Оплата:*
• 1 запрос = 5 Telegram Stars
• Оплата через Telegram Stars
• Сразу после оплаты запросы добавляются

🎯 *Модели:*
• *ChatGPT* - GPT-5 от OpenAI
• *Claude 4.5* - Sonnet от Anthropic
• *Gemini* - Pro от Google
• *DeepSeek* - Chat от DeepSeek"""
    
    await update.message.reply_text(text.format(ADMIN_ID=ADMIN_ID), parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = user_db.get_user(user_id)
    
    if user['requests_left'] <= 0:
        text = """❌ *Недостаточно запросов!*

💰 Ваш баланс: 0 запросов

🛒 *Пополните баланс:* /buy
• 1 запрос = 5⭐
• 10 запросов = 50⭐ (+1 бонус)
• 100 запросов = 500⭐ (+5 бонусов)"""
        
        keyboard = [
            [InlineKeyboardButton("🛒 Купить запросы", callback_data='buy')],
            [InlineKeyboardButton("💰 Баланс", callback_data='balance')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    message_text = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    response = await ai_client.send_request(user_id, message_text)
    
    if response:
        user_db.update_user(user_id, {
            "requests_left": user['requests_left'] - 1,
            "total_requests": user['total_requests'] + 1
        })
        
        remaining = user['requests_left'] - 1
        
        if len(response) > 4000:
            chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
            await update.message.reply_text(f"*Ответ AI:*\n\n{chunks[0]}\n\n📊 *Осталось запросов:* {remaining}", parse_mode='Markdown')
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(f"*Ответ AI:*\n\n{response}\n\n📊 *Осталось запросов:* {remaining}", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Ошибка при получении ответа. Попробуйте еще раз.")

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    try:
        if payload.startswith("package_"):
            parts = payload.split("_")
            if len(parts) >= 3:
                package_type = parts[1]
                user_id = int(parts[2])
                
                packages = {
                    "1": 1,
                    "5": 5,
                    "10": 11,
                    "100": 105
                }
                
                if package_type in packages:
                    user_db.add_requests(user_id, packages[package_type])
                    
                    user = user_db.get_user(user_id)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ *Оплата прошла успешно!*\n\n📦 Добавлено: {packages[package_type]} запросов\n💰 Новый баланс: {user['requests_left']} запросов\n\nСпасибо за покупку! 🎉",
                        parse_mode='Markdown'
                    )
    except Exception as e:
        logger.error(f"Payment processing error: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'select_model':
        await show_model_selection(update, context)
    
    elif query.data == 'balance':
        await balance_command(update, context)
    
    elif query.data == 'buy':
        await buy_command(update, context)
    
    elif query.data == 'help':
        await help_command(update, context)
    
    elif query.data == 'back':
        await start(update, context)
    
    elif query.data.startswith('set_'):
        model_map = {
            'set_chatgpt': 'chatgpt',
            'set_claude': 'claude',
            'set_gemini': 'gemini',
            'set_deepseek': 'deepseek'
        }
        
        if query.data in model_map:
            user_db.update_user(user_id, {"selected_model": model_map[query.data]})
            model_names = {
                'chatgpt': 'ChatGPT',
                'claude': 'Claude 3',
                'gemini': 'Gemini Pro',
                'deepseek': 'DeepSeek'
            }
            await query.edit_message_text(f"✅ Выбрана модель: {model_names[model_map[query.data]]}")
    
    elif query.data.startswith('invoice_'):
        package_type = query.data.replace('invoice_', '')
        await create_invoice(update, context, package_type)

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    if not PROXYAPI_KEY:
        raise ValueError("PROXYAPI_KEY не установлен")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
