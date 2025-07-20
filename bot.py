import os
import random
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    JobQueue, CallbackQueryHandler
)
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from bs4 import BeautifulSoup

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")

# Set the group or channel chat id where suggestions should be posted
CHAT_ID = int(os.getenv("CHAT_ID", "-100xxxxxxxxxx"))  # fill with real chat id

# Download links
FREE_DOWNLOAD_LINK = "https://your-free-download-link.com"
PAID_DOWNLOAD_LINK = "https://your-paid-download-link.com"

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


# === HELPER FUNCTIONS ===

def get_trending_bollywood_movies():
    """Scrape IMDb for trending Bollywood movies (India Trending page)."""
    url = "https://www.imdb.com/india/trending/"
    headers = {"User-Agent": "Mozilla/5.0"}
    movies = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup.select(".ipc-poster-card__title"):
            t = tag.get_text(strip=True)
            if t and t not in movies:
                movies.append(t)
    except Exception as e:
        print(f"Error fetching movies: {e}")
    return movies or ["No trending movie right now"]

def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"Error generating AI response: {e}")
        return "Error generating AI response."

async def delete_bot_message(context):
    data = context.job.data
    message = data.get("message")
    if message:
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = "Hello!"
    welcome_text = (
        f"{greeting} 😊\n\nType a movie name any time!\n"
        f"Use /ai <your question> for AI help."
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
            f"🎞️ *Cast*: {data.get('Actors')}\n"
        )
        poster_url = data.get("Poster")
        download_button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")]]
        )
        if poster_url != "N/A":
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=reply_text,
                parse_mode="Markdown",
                reply_markup=download_button
            )
        else:
            message = await update.message.reply_text(
                reply_text,
                parse_mode="Markdown",
                reply_markup=download_button
            )
    else:
        ai_response = generate_ai_content(f"Can you describe the movie '{movie_name}'?")
        message = await update.message.reply_text(
            f"Movie not found in IMDb. Here's an AI-generated description👇:\n\n{ai_response}😊"
        )
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

# === SUGGESTION JOB ===

async def send_movie_suggestion(context: ContextTypes.DEFAULT_TYPE):
    trending_movies = get_trending_bollywood_movies()
    if trending_movies and trending_movies[0] != "No trending movie right now":
        suggestion = random.choice(trending_movies)
    else:
        suggestion = "Coolie"  # fallback
    # Send suggestion message with download button
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download", callback_data=f"suggest_download_{suggestion.replace(' ', '_')}")]
    ])
    msg = await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🎬 Trending Bollywood Movie Suggestion:\n\n*{suggestion}*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})

async def handle_suggest_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

# === MAIN ===

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern="^download_"))
    app.add_handler(CallbackQueryHandler(handle_suggest_download_callback, pattern="^suggest_download_"))
    # Suggestion job: every 10 minutes
    app.job_queue.run_repeating(send_movie_suggestion, interval=600, first=10)
    # Webhook setup
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
