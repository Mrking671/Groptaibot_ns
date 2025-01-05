import os
import requests
import google.generativeai as genai
from telegram import Update, Reaction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
from datetime import timedelta

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default to the provided IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Default Gemini API key

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Welcome new users
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        # Fetch user profile photos
        photos = await context.bot.get_user_profile_photos(new_member.id)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][0].file_id
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=photo_file_id,
                caption=f"Welcome, {new_member.full_name}!",
            )
        else:
            await update.message.reply_text(f"Welcome, {new_member.full_name}!")

# IMDb information fetcher
async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await context.bot.send_photo(chat_id=update.message.chat_id, photo=poster_url, caption=reply_text, parse_mode="Markdown")
        else:
            await update.message.reply_text(reply_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("Movie not found. Please check the name and try again.")

# AI response using Gemini API
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Please provide a question. Usage: /ai <your question>")
        return

    question = " ".join(context.args)
    try:
        response = model.generate_content(question)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

# Auto-delete feature (after 5 minutes)
async def auto_delete_message(context: ContextTypes.DEFAULT_TYPE, job):
    job.context.delete_message(chat_id=job.context.chat.id, message_id=job.context.message_id)

async def auto_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    # Schedule the deletion after 5 minutes (300 seconds)
    context.job_queue.run_once(auto_delete_message, 300, context=message)

# Add a reaction to every message
async def add_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # You can choose to add a sticker or an emoji reaction
    await update.message.react("👍")  # Add thumbs-up emoji reaction

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT, add_reaction))  # Reaction on every message
    app.add_handler(MessageHandler(filters.TEXT, auto_delete))  # Auto-delete after 5 minutes

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
