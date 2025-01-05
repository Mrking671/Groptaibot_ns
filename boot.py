import os
import requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default to the provided IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Default Gemini API key

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Function to delete messages
async def delete_message(context: CallbackContext) -> None:
    await context.bot.delete_message(chat_id=context.job.context["chat_id"], message_id=context.job.context["message_id"])

# Welcome new users
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        # Fetch user profile photos
        photos = await context.bot.get_user_profile_photos(new_member.id)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][0].file_id
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=photo_file_id,
                caption=f"Welcome, {new_member.full_name}!",
            )
        else:
            message = await update.message.reply_text(f"Welcome, {new_member.full_name}!")
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})

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
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})
    else:
        message = await update.message.reply_text("Movie not found. Please check the name and try again.")
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})

# AI response using Gemini API
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question>")
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})
        return

    question = " ".join(context.args)
    try:
        response = model.generate_content(question)
        message = await update.message.reply_text(response.text)
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})
    except Exception as e:
        message = await update.message.reply_text(f"An error occurred: {e}")
        
        # Schedule message deletion
        context.job_queue.run_once(delete_message, 30, context={"chat_id": message.chat_id, "message_id": message.message_id})

# Main function
def main():
    # Create Application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add job queue
    app.job_queue = app.job_queue

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
