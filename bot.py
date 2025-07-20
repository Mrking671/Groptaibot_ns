import os
import random
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler
)
from datetime import datetime
from bs4 import BeautifulSoup

# ========== CONFIGURATION ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHAT_ID = int(os.getenv("CHAT_ID", "-1001878181555"))   # Replace with your group/channel/chat id

FREE_DOWNLOAD_LINK = "https://your-free-download-link.com"   # Set your free link
PAID_DOWNLOAD_LINK = "https://your-paid-download-link.com"   # Set your paid link

# === Google Gemini AI Model setup ===
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ========== HELPERS ==========

def get_trending_bollywood_movies():
    url = "https://www.imdb.com/india/trending/"
    headers = {"User-Agent": "Mozilla/5.0"}
    movies = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ["No trending movie right now"]
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup.select(".ipc-poster-card__title"):
            t = tag.get_text(strip=True)
            if t and t not in movies:
                movies.append(t)
    except Exception as e:
        print(f"Error fetching movies: {e}")
        return ["No trending movie right now"]
    return movies or ["No trending movie right now"]

def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"AI error: {e}")
        return "AI error."

async def delete_bot_message(context):
    data = context.job.data
    message = data.get("message")
    if message:
        try:
            await message.delete()
        except Exception:
            pass

def get_time_based_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good Morning!"
    elif 12 <= hour < 18:
        return "Good Afternoon!"
    elif 18 <= hour < 22:
        return "Good Evening!"
    else:
        return "Good Night!"

# ========== HANDLERS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = (
        f"{greeting} 😊\n\nType a movie name any time!\nUse /ai <your question> for AI help."
    )
    message = await update.message.reply_text(welcome_text)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question> 😊")
        context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        return
    question = " ".join(context.args)
    ai_reply = generate_ai_content(question)
    message = await update.message.reply_text(ai_reply)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    movie_name = update.message.text.strip()
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if data.get("Response") == "True":
        reply_text = (
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n\n\n"
        )
        fun_fact_prompt = f"Give me some fun facts about the movie {movie_name}."
        fun_fact = generate_ai_content(fun_fact_prompt)
        final_text = reply_text + fun_fact
        poster_url = data.get("Poster")
        download_button = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_button = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_button], [next_button]])

        await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=poster_url,
            caption=final_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    else:
        trending = get_trending_bollywood_movies()
        import difflib
        close = difflib.get_close_matches(movie_name, trending, n=1, cutoff=0.6)
        if close:
            corrected = close[0]
            ai_prompt = f"Describe the movie '{corrected}'."
            ai_text = generate_ai_content(ai_prompt)
            reply_text = f"Did you mean **{corrected}** ?\n\n{ai_text}"
            await update.message.reply_text(reply_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("Movie not found and no good alternative suggestion found.")

        # Trending suggestion buttons
        buttons = [
            [InlineKeyboardButton(m, callback_data=f"suggest_{m.replace(' ','_')}")]
            for m in trending[:3]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Trending Bollywood Movies:", reply_markup=reply_markup)

    context.job_queue.run_once(delete_bot_message, 300, data={"message": update.message})

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

# For cycling trending movies between suggestions
suggestion_index = 0

async def send_movie_suggestion(context: ContextTypes.DEFAULT_TYPE):
    global suggestion_index
    trending_movies = get_trending_bollywood_movies()
    if not trending_movies or trending_movies[0] == "No trending movie right now":
        trending_movies = ["Coolie"]

    if suggestion_index >= len(trending_movies):
        suggestion_index = 0

    movie_name = trending_movies[suggestion_index]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)

    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if data.get("Response") == "True":
        reply_text = (
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n\n\n"
        )
        fun_fact_prompt = f"Give me some fun facts about the movie {movie_name}."
        fun_fact = generate_ai_content(fun_fact_prompt)
        final_text = reply_text + fun_fact
        poster_url = data.get("Poster")
        download_button = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_button = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_button], [next_button]])

        msg = await context.bot.send_photo(
            chat_id=CHAT_ID,
            photo=poster_url,
            caption=final_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})

async def handle_suggest_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_movie_suggestion(context)
    try:
        await query.message.delete()
    except Exception:
        pass

# ========== MAIN APP ==========

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern="^download_"))
    app.add_handler(CallbackQueryHandler(handle_suggest_next, pattern="^suggest_next"))
    app.job_queue.run_repeating(send_movie_suggestion, interval=600, first=10)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
