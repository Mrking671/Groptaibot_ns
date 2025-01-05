import logging
import os
import requests
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.error import BadRequest

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Set as environment variable
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Render webhook URL
IMDB_API_KEY = os.getenv("IMDB_API_KEY")  # IMDb API key
GEMINI_API_URL = os.getenv("GEMINI_API_URL")  # Gemini API endpoint

# Bot instance
bot = Bot(token=BOT_TOKEN)

# Welcome new users with DP
async def welcome(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        user_name = member.first_name or "User"
        try:
            # Fetch user profile photo
            photos = await bot.get_user_profile_photos(member.id)
            if photos.total_count > 0:
                photo = photos.photos[0][-1]  # Get highest resolution photo
                file = await bot.get_file(photo.file_id)
                file_path = file.file_path
                
                # Download and send DP with welcome message
                await bot.send_photo(
                    chat_id=update.message.chat.id,
                    photo=file_path,
                    caption=f"Welcome {user_name} to the group!",
                )
            else:
                await update.message.reply_text(f"Welcome {user_name} to the group!")
        except BadRequest:
            await update.message.reply_text(f"Welcome {user_name} to the group!")

# IMDb Info
async def fetch_imdb_info(update: Update, context: CallbackContext):
    movie_name = " ".join(context.args)
    if not movie_name:
        await update.message.reply_text("Please provide a movie name.")
        return

    # Fetch IMDb info
    imdb_url = f"https://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(imdb_url).json()
    if response.get("Response") == "True":
        movie_info = (
            f"🎥 *{response['Title']}* ({response['Year']})\n"
            f"⭐ *Rating*: {response['imdbRating']}\n"
            f"🎭 *Actors*: {response['Actors']}\n"
            f"📝 *Plot*: {response['Plot']}\n"
        )
        await update.message.reply_text(movie_info, parse_mode="Markdown")
    else:
        await update.message.reply_text("Movie not found.")

# AI Responses using Gemini
async def ai_response(update: Update, context: CallbackContext):
    user_input = " ".join(context.args)
    if not user_input:
        await update.message.reply_text("Please provide text to get a response.")
        return

    response = requests.get(f"{GEMINI_API_URL}?text={user_input}").json()
    ai_reply = response.get("response", "Sorry, I couldn't process your request.")
    await update.message.reply_text(ai_reply)

# Main setup
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CommandHandler("imdb", fetch_imdb_info))
    app.add_handler(CommandHandler("ai", ai_response))

    # Webhook setup
    app.run_webhook(
        listen="0.0.0.0",
        port=8443,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
