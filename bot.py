import os
import requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Gemini API key

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Function to generate AI content using Gemini API
def generate_ai_content(prompt: str) -> str:
    try:
        response = genai.generate_text(model="models/text-bison-001", prompt=prompt)
        return response["candidates"][0]["output"] if response["candidates"] else "No response generated."
    except Exception as e:
        return f"Error generating AI response: {e}"

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
    message = await update.message.reply_text(welcome_text)

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# IMDb information fetcher
async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return  # Ignore updates without a text message

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
            message = await context.bot.send_photo(chat_id=update.message.chat.id, photo=poster_url, caption=reply_text)
        else:
            message = await update.message.reply_text(reply_text)
    else:
        ai_reply = generate_ai_content(f"Tell me about the movie {movie_name}")
        message = await update.message.reply_text(f"AI Response:\n{ai_reply}")

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Function to delete bot's own messages
async def delete_bot_message(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    message = data.get("message")

    if message:
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

# AI response using Gemini API
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question>")
        context.job_queue.run_once(delete_bot_message, 30, data={"message": message})
        return

    question = " ".join(context.args)
    ai_reply = generate_ai_content(question)
    message = await update.message.reply_text(ai_reply)

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
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
