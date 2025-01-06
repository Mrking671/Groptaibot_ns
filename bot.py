import os
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from datetime import datetime
from langdetect import detect
from PIL import Image, ImageDraw, ImageFont
import io

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Default Gemini API key
DOWNLOAD_LINK = os.getenv("DOWNLOAD_LINK", "https://example.com/download?id=YOUR_ID")  # Default download link

# Configure Gemini API and model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Function to generate AI content
def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"Error generating AI response: {e}")
        return "Error generating AI response."

# Function to delete bot's own messages
async def delete_bot_message(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    message = data.get("message")

    if message:
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

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

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = f"{greeting}\n\nI'm your friendly bot! How can I assist you today?"
    message = await update.message.reply_text(welcome_text)

    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Welcome all users (new or existing)
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    # Fetch user profile photos
    photos = await context.bot.get_user_profile_photos(user.id)
    if photos.total_count > 0:
        # Get the first photo
        photo_file_id = photos.photos[0][0].file_id
        photo = await context.bot.get_file(photo_file_id)

        # Download the image
        photo_path = photo.file_path
        photo_data = await context.bot.download_file(photo_path)

        # Open the user's photo using Pillow
        user_photo = Image.open(io.BytesIO(photo_data)).resize((100, 100)).convert("RGBA")

        # Create a circular mask
        mask = Image.new("L", user_photo.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + user_photo.size, fill=255)
        circular_photo = Image.new("RGBA", user_photo.size)
        circular_photo.paste(user_photo, mask=mask)

        # Create a rectangular background
        background = Image.new('RGB', (500, 250), (255, 255, 255))
        draw_bg = ImageDraw.Draw(background)
        draw_bg.rectangle([(10, 10), (490, 240)], outline="blue", width=5)

        # Paste circular photo onto the background
        background.paste(circular_photo, (50, 75), circular_photo)

        # Add text (welcome message, name, and user ID)
        draw_bg.text((200, 50), f"Welcome, {user.full_name}!", fill="black")
        draw_bg.text((200, 100), f"User ID: {user.id}", fill="gray")
        draw_bg.text((200, 150), "We're happy to have you here!", fill="black")

        # Save the final image to a bytes buffer
        byte_io = io.BytesIO()
        background.save(byte_io, format='PNG')
        byte_io.seek(0)

        # Send the welcome image
        message = await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=byte_io,
            caption="Enjoy your stay!"
        )
    else:
        # If no profile photo, just send a text message
        message = await update.message.reply_text(f"Welcome, {user.full_name}!")

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

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
            f"👥 *Actors*: {data.get('Actors')}\n"
            f"🌟 *Awards*: {data.get('Awards')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
        )
        poster_url = data.get("Poster")

        # Add inline keyboard with download button
        keyboard = [
            [InlineKeyboardButton("Download Now", url=DOWNLOAD_LINK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if poster_url != "N/A":
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=reply_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            message = await update.message.reply_text(
                reply_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    else:
        ai_reply = generate_ai_content("Movie not found: " + movie_name)
        message = await update.message.reply_text(ai_reply)

    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# AI response command
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
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.MEMBER_STATUS, welcome))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
