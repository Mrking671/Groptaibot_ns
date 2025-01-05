import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY")
GEMINI_API_URL = os.getenv("GEMINI_API_URL")

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
    movie_name = update.message.text
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
    response = requests.get(f"{GEMINI_API_URL}?text={question}")
    data = response.json()

    if "response" in data:
        await update.message.reply_text(data["response"])
    else:
        await update.message.reply_text("Sorry, I couldn't process your request.")

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(CommandHandler("ai", ai_response))

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
