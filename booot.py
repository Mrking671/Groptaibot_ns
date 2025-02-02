import os
import requests
import google.generativeai as genai
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
from langdetect import detect
from PIL import Image, ImageDraw, ImageFont

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Default Gemini API key

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

# Start command: Send a custom start message with the time-based greeting
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = f"{greeting}\n\nI'm your friendly bot! How can I assist you today?"
    message = await update.message.reply_text(welcome_text)

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
            f"📝 *Plot*: {data.get('Plot')}\n"
        )
        poster_url = data.get("Poster")
        if poster_url != "N/A":
            message = await context.bot.send_photo(chat_id=update.message.chat_id, photo=poster_url, caption=reply_text, parse_mode="Markdown")
        else:
            message = await update.message.reply_text(reply_text, parse_mode="Markdown")
    else:
        # Fallback to AI response if movie not found
        ai_reply = generate_ai_content(f"Suggest popular movies similar to {movie_name}.")
        message = await update.message.reply_text(ai_reply)

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Welcome new users and add DP inside rectangular background image
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        # Fetch user profile photos
        photos = await context.bot.get_user_profile_photos(new_member.id)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][0].file_id
            photo_file = await context.bot.get_file(photo_file_id)
            photo_path = f"{new_member.id}_photo.jpg"
            await photo_file.download_to_drive(photo_path)

            # Create a custom welcome image
            bg_image = Image.new("RGB", (600, 300), (255, 255, 255))
            draw = ImageDraw.Draw(bg_image)
            font = ImageFont.load_default()

            # Add text
            draw.text((20, 20), f"Welcome, {new_member.full_name}!", fill="black", font=font)

            # Add DP to the background
            user_photo = Image.open(photo_path).resize((100, 100))
            bg_image.paste(user_photo, (20, 100))

            # Save and send image
            welcome_image_path = f"{new_member.id}_welcome.jpg"
            bg_image.save(welcome_image_path)
            message = await context.bot.send_photo(chat_id=update.message.chat_id, photo=InputFile(welcome_image_path))

            os.remove(photo_path)
            os.remove(welcome_image_path)
        else:
            message = await update.message.reply_text(f"Welcome, {new_member.full_name}!")

        # Schedule deletion after 30 seconds
        context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Admin commands (Mute user)
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        message = await update.message.reply_text("Reply to a user's message to mute them.")
        context.job_queue.run_once(delete_bot_message, 30, data={"message": message})
        return

    user_id = update.message.reply_to_message.from_user.id
    await context.bot.restrict_chat_member(chat_id=update.message.chat_id, user_id=user_id, permissions={})
    message = await update.message.reply_text(f"User {update.message.reply_to_message.from_user.full_name} has been muted.")
    context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

# Keyword triggers
KEYWORDS = {"hello": "Hi there! How can I help you?", "rules": "Please follow the group rules: Be respectful, no spamming."}

async def keyword_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for keyword, response in KEYWORDS.items():
        if keyword in update.message.text.lower():
            message = await update.message.reply_text(response)
            context.job_queue.run_once(delete_bot_message, 30, data={"message": message})
            return

# Multi-language support
async def multi_language_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    detected_language = detect(update.message.text)
    if detected_language != "en":
        translated_text = generate_ai_content(f"Translate this to English: {update.message.text}")
        message = await update.message.reply_text(f"Translation: {translated_text}")
        context.job_queue.run_once(delete_bot_message, 30, data={"message": message})

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
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), keyword_trigger))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), multi_language_response))

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
