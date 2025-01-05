import os
import requests
import google.generativeai as genai
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
)
from datetime import datetime

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Gemini API key

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Custom greeting based on time of day
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

# Start command: Send a custom start message with the time-based greeting
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = f"{greeting}\n\nI'm your friendly bot! How can I assist you today?"
    sent_message = await update.message.reply_text(welcome_text)
    schedule_message_deletion(context, sent_message.chat_id, sent_message.message_id)

# Function to schedule message deletion
def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    # Schedule the message to be deleted after 60 seconds
    context.job_queue.run_once(
        delete_message, when=60, context={"chat_id": chat_id, "message_id": message_id}
    )

# Function to delete a specific message
async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.context
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Failed to delete message {message_id} in chat {chat_id}: {e}")

# IMDb information fetcher
async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
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
            )
            poster_url = data.get("Poster")
            if poster_url != "N/A":
                sent_message = await context.bot.send_photo(
                    chat_id=update.message.chat.id,
                    photo=poster_url,
                    caption=reply_text,
                )
            else:
                sent_message = await update.message.reply_text(reply_text)
        else:
            ai_response = model.generate_content(f"Tell me about the movie {movie_name}")
            sent_message = await update.message.reply_text(
                f"IMDb couldn't find this movie, but here's what I found: \n\n{ai_response.text}"
            )
        # Schedule deletion of the response message
        schedule_message_deletion(context, sent_message.chat_id, sent_message.message_id)
    else:
        sent_message = await update.message.reply_text("Please provide a movie name.")
        schedule_message_deletion(context, sent_message.chat_id, sent_message.message_id)

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))

    # Run webhook
    app.run_webhook(
        listen="0.0.0.0",  # Listen on all interfaces
        port=int(os.getenv("PORT", 8443)),  # Use Render's PORT or default to 8443
        url_path=BOT_TOKEN,  # Bot token as URL path
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",  # Full webhook URL
    )

# Entry point
if __name__ == "__main__":
    main()
