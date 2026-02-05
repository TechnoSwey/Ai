import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
import aiohttp
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("PROXYAPI_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

users_file = "users.json"

def load_users():
    try:
        with open(users_file, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(users_file, 'w') as f:
        json.dump(users, f, indent=2)

async def get_model_response(model, prompt):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    endpoints = {
        "chatgpt": "https://api.proxyapi.ru/openai/v1/chat/completions",
        "deepseek": "https://api.proxyapi.ru/openai/v1/chat/completions",
        "claude": "https://api.proxyapi.ru/anthropic/v1/messages",
        "gemini": "https://api.proxyapi.ru/google/v1/models/gemini-pro:generateContent"
    }
    
    model_names = {
        "chatgpt": "gpt-4-turbo-preview",
        "deepseek": "deepseek-chat",
        "claude": "claude-3-haiku-20240307",
        "gemini": "gemini-pro"
    }
    
    url = endpoints[model]
    
    try:
        async with aiohttp.ClientSession() as session:
            if model == "chatgpt" or model == "deepseek":
                payload = {
                    "model": model_names[model],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    return data['choices'][0]['message']['content']
            
            elif model == "claude":
                headers["x-api-key"] = API_KEY
                headers["anthropic-version"] = "2023-06-01"
                headers["Content-Type"] = "application/json"
                
                payload = {
                    "model": model_names[model],
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    return data['content'][0]['text']
            
            elif model == "gemini":
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
    
    except Exception as e:
        logger.error(f"API error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user_id = str(update.effective_user.id)
    
    if user_id not in users:
        users[user_id] = {
            "requests_left": 0,
            "selected_model": "chatgpt",
            "total_used": 0
        }
        save_users(users)
    
    requests_left = users[user_id]["requests_left"]
    
    text = f"""🤖 Привет! Выбери модель:

📊 Баланс: {requests_left} запросов
💎 1 запрос = 5⭐

Модели:
• ChatGPT (GPT-4)
• Claude 3
• Gemini Pro
• DeepSeek

Команды:
/balance - Баланс
/buy - Купить запросы
/model - Сменить модель"""

    keyboard = [
        [InlineKeyboardButton("🤖 ChatGPT", callback_data="select_chatgpt")],
        [InlineKeyboardButton("🧠 Claude", callback_data="select_claude")],
        [InlineKeyboardButton("⭐ Gemini", callback_data="select_gemini")],
        [InlineKeyboardButton("🚀 DeepSeek", callback_data="select_deepseek")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance"), InlineKeyboardButton("🛒 Купить", callback_data="buy")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user_id = str(update.effective_user.id)
    
    if user_id not in users:
        requests_left = 0
        total_used = 0
    else:
        requests_left = users[user_id]["requests_left"]
        total_used = users[user_id]["total_used"]
    
    text = f"""💰 Баланс

Доступно: {requests_left} запросов
Использовано: {total_used}

💎 Тарифы:
• 1 запрос = 5⭐
• 5 запросов = 25⭐
• 10 запросов = 50⭐ (+1 бонус)
• 100 запросов = 500⭐ (+5 бонусов)

/buy - Купить запросы"""
    
    keyboard = [[InlineKeyboardButton("🛒 Купить", callback_data="buy"), InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🛒 Купить запросы

💎 Выбери пакет:
• 1 запрос = 5⭐
• 5 запросов = 25⭐
• 10 запросов = 50⭐ (+1 бонусный)
• 100 запросов = 500⭐ (+5 бонусных)

Нажми на кнопку для оплаты"""
    
    keyboard = [
        [InlineKeyboardButton("1 запрос (5⭐)", callback_data="invoice_1")],
        [InlineKeyboardButton("5 запросов (25⭐)", callback_data="invoice_5")],
        [InlineKeyboardButton("10 запросов (50⭐)", callback_data="invoice_10")],
        [InlineKeyboardButton("100 запросов (500⭐)", callback_data="invoice_100")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    user_id = str(query.from_user.id)
    
    if query.data == "balance":
        await balance_command(update, context)
    
    elif query.data == "buy":
        await buy_command(update, context)
    
    elif query.data == "back":
        await start(update, context)
    
    elif query.data.startswith("select_"):
        model = query.data.replace("select_", "")
        users[user_id]["selected_model"] = model
        
        model_names = {
            "chatgpt": "ChatGPT",
            "claude": "Claude 3",
            "gemini": "Gemini Pro",
            "deepseek": "DeepSeek"
        }
        
        save_users(users)
        await query.edit_message_text(f"✅ Выбрана модель: {model_names[model]}")
    
    elif query.data.startswith("invoice_"):
        package = query.data.replace("invoice_", "")
        
        prices = {
            "1": 5,
            "5": 25,
            "10": 50,
            "100": 500
        }
        
        requests = {
            "1": 1,
            "5": 5,
            "10": 11,
            "100": 105
        }
        
        if package in prices:
            try:
                await context.bot.send_invoice(
                    chat_id=query.from_user.id,
                    title=f"Пакет {package} запросов",
                    description=f"{requests[package]} запросов к AI",
                    payload=f"package_{package}_{user_id}",
                    currency="XTR",
                    prices=[{"label": "Запросы", "amount": prices[package]}],
                    start_parameter="ai_bot"
                )
            except Exception as e:
                logger.error(f"Invoice error: {e}")
                await query.message.reply_text("❌ Ошибка создания счета")

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith("package_"):
        parts = payload.split("_")
        if len(parts) == 3:
            package = parts[1]
            user_id = parts[2]
            
            requests_add = {
                "1": 1,
                "5": 5,
                "10": 11,
                "100": 105
            }
            
            if package in requests_add:
                users = load_users()
                if user_id in users:
                    users[user_id]["requests_left"] += requests_add[package]
                else:
                    users[user_id] = {
                        "requests_left": requests_add[package],
                        "selected_model": "chatgpt",
                        "total_used": 0
                    }
                
                save_users(users)
                
                await update.message.reply_text(
                    f"✅ Оплачено!\nДобавлено: {requests_add[package]} запросов\nБаланс: {users[user_id]['requests_left']} запросов"
                )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    user_id = str(update.effective_user.id)
    
    if user_id not in users or users[user_id]["requests_left"] <= 0:
        await update.message.reply_text(
            "❌ Нет запросов!\n/buy - купить запросы\n/balance - проверить баланс"
        )
        return
    
    selected_model = users[user_id]["selected_model"]
    prompt = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    response = await get_model_response(selected_model, prompt)
    
    if response:
        users[user_id]["requests_left"] -= 1
        users[user_id]["total_used"] += 1
        save_users(users)
        
        remaining = users[user_id]["requests_left"]
        
        if len(response) > 4000:
            chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
            await update.message.reply_text(f"Ответ:\n{chunks[0]}\n\nОсталось: {remaining}")
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(f"Ответ:\n{response}\n\nОсталось: {remaining}")
    else:
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    if not API_KEY:
        raise ValueError("PROXYAPI_KEY не установлен")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("model", buy_command))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
