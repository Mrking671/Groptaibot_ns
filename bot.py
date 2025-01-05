import os
import requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
from telegram import ParseMode

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
    await update.message.reply_text(welcome_text)

# Admin command: Kick a user
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == 22711559:  # Replace with actual admin user ID
        if len(context.args) == 1:
            user_id = int(context.args[0])
            await context.bot.kick_chat_member(update.message.chat.id, user_id)
            await update.message.reply_text(f"User {user_id} has been kicked.")
        else:
            await update.message.reply_text("Please provide a user ID to kick.")
    else:
        await update.message.reply_text("You are not authorized to use this command.")

# Admin command: Clear chat
async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_USER_ID:  # Replace with actual admin user ID
        await context.bot.delete_messages(update.message.chat.id, [message.message_id for message in update.message.chat.messages])
        await update.message.reply_text("Chat cleared.")
    else:
        await update.message.reply_text("You are not authorized to use this command.")

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
        # IMDb movie not found, ask AI for details
        ai_response = model.generate_content(f"Tell me about the movie {movie_name}")
        await update.message.reply_text(f"IMDb couldn't find this movie, but here's what I found: \n\n{ai_response.text}")

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

# Add reactions with multiple emojis on every message
async def add_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reactions = "❤🖐😊😂👍"  # Multiple emoji reactions
    await update.message.reply_text(reactions)  # Send the reactions as a message

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
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
