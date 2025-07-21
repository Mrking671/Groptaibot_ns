import os
import random
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from bs4 import BeautifulSoup
import difflib

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")

# For automated suggestions - set your chat/group ID
CHAT_ID = int(os.getenv("CHAT_ID", "-1001234567890"))  # Replace with your actual chat ID

# Download links
FREE_DOWNLOAD_LINK = "https://your-free-download-link.com"
PAID_DOWNLOAD_LINK = "https://your-paid-download-link.com"

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Global variable for suggestion cycling
suggestion_index = 0

# Function to generate AI content
def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"Error generating AI response: {e}")
        return "Error generating AI response."

# Function to get trending Bollywood movies from IMDb
def get_trending_bollywood_movies():
    """Scrape IMDb trending page for Bollywood movies"""
    url = "https://www.imdb.com/india/trending/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    movies = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            # Updated selector based on current IMDb structure
            for tag in soup.select(".ipc-poster-card__title"):
                title = tag.get_text(strip=True)
                if title and title not in movies:
                    movies.append(title)
    except Exception as e:
        print(f"Error fetching trending movies: {e}")
    
    # Fallback movies if scraping fails
    return movies or ["Coolie", "War 2", "Kingdom", "Mahavatar Narsimha", "Son of Sardaar 2"]

# Function to delete bot's messages after a delay
async def delete_bot_message(context):
    data = context.job.data
    message = data.get("message")
    if message:
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

# Greeting based on time of day
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
    welcome_text = f"{greeting}😊\n\nɪ'ᴍ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɪ ʙᴏᴛ ʜᴇʟᴘ ʏᴏᴜ ᴛᴏ ғɪɴᴅ ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴍᴏᴠɪᴇs ᴅᴇᴛᴀɪʟs.\nᴊᴜsᴛ ᴛʏᴘᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ʏᴏᴜ ᴍᴏᴠɪᴇ ᴅᴇᴛᴀɪʟs ᴀs ᴡᴇʟʟ ᴀs ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ.\n\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗.\n𝗠𝗔𝗗𝗘 𝗪𝗜𝗧𝗛 ❤ 𝗯𝘆 @Lordsakunaa"
    message = await update.message.reply_text(welcome_text)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

# Welcome new members with custom square image
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        user_name = new_member.full_name or "Unknown User"
        user_id = new_member.id
        username = new_member.username or "No Username"

        # Fetch user profile photo
        try:
            photos = await context.bot.get_user_profile_photos(user_id)
            if photos.total_count > 0:
                photo_file = await context.bot.get_file(photos.photos[0][0].file_id)
                photo_bytes = await photo_file.download_as_bytearray()
                user_photo = Image.open(io.BytesIO(photo_bytes))
            else:
                user_photo = Image.new("RGB", (400, 400), (128, 128, 128))
        except Exception as e:
            print(f"Error fetching profile photo: {e}")
            user_photo = Image.new("RGB", (400, 400), (128, 128, 128))

        # Create a square image (400x400) with circular DP
        background = Image.new("RGB", (400, 400), "white")
        draw = ImageDraw.Draw(background)
        user_photo = user_photo.resize((300, 300)).convert("RGBA")
        mask = Image.new("L", user_photo.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + user_photo.size, fill=255)
        background.paste(user_photo, (50, 50), mask)

        # Add username at the bottom center
        try:
            font = ImageFont.truetype(random.choice(["arial.ttf", "times.ttf", "calibri.ttf"]), 24)
        except IOError:
            font = ImageFont.load_default()

        text_bbox = font.getbbox(user_name)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (400 - text_width) // 2
        draw.text((text_x, 350), user_name, fill="black", font=font, align="center")

        # Save and send the image
        output = io.BytesIO()
        background.save(output, format="PNG")
        output.seek(0)

        try:
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=output,
                caption=f"𝐖𝐄𝐋𝐂𝐎𝐌𝐄❤\n\n👤 Name: {user_name}\n🆔 ID: {user_id}\n🔗 Username: @{username}\n\nᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ɪᴛ ᴛᴏ ʏᴏᴜ😊\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗"
            )
            context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        except Exception as e:
            print(f"Error sending welcome image: {e}")

# Enhanced movie info fetcher with AI correction
async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    movie_name = update.message.text.strip()
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if data.get("Response") == "True":
        # Movie found - show full details with fun facts
        details = (
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n\n\n"
        )
        
        # Get AI-generated fun facts
        fun_facts = generate_ai_content(f"Give me some interesting fun facts about the movie {data.get('Title')}.")
        final_caption = details + fun_facts
        
        poster_url = data.get("Poster")
        download_button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")]]
        )

        if poster_url and poster_url != "N/A":
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=final_caption,
                parse_mode="Markdown",
                reply_markup=download_button
            )
        else:
            message = await update.message.reply_text(
                final_caption,
                parse_mode="Markdown",
                reply_markup=download_button
            )
    else:
        # Movie not found - try AI correction
        trending_movies = get_trending_bollywood_movies()
        close_matches = difflib.get_close_matches(movie_name, trending_movies, n=1, cutoff=0.6)
        
        if close_matches:
            corrected_movie = close_matches[0]
            correction_prompt = f"The user searched for '{movie_name}' but I think they meant '{corrected_movie}'. Provide the corrected movie name in bold and give a brief description of the movie."
            ai_response = generate_ai_content(correction_prompt)
        else:
            correction_prompt = f"The user searched for a movie called '{movie_name}' but it wasn't found. Suggest the most likely correct movie name in bold and provide some details about it."
            ai_response = generate_ai_content(correction_prompt)
        
        message = await update.message.reply_text(
            ai_response,
            parse_mode="Markdown"
        )
        
        # Show trending movie suggestions
        trending_buttons = [
            [InlineKeyboardButton(movie, callback_data=f"suggest_{movie.replace(' ', '_')}")]
            for movie in trending_movies[:3]
        ]
        await update.message.reply_text(
            "🎬 **Trending Bollywood Movies:**",
            reply_markup=InlineKeyboardMarkup(trending_buttons),
            parse_mode="Markdown"
        )

    # Schedule deletion after 5 minutes
    context.job_queue.run_once(delete_bot_message, 300, data={"message": message})

# Download button callback handler
async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

# Automated movie suggestion function
async def send_movie_suggestion(context: ContextTypes.DEFAULT_TYPE):
    global suggestion_index
    
    trending_movies = get_trending_bollywood_movies()
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
    
    # Get movie details from OMDb
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()
    
    if data.get("Response") == "True":
        details = (
            f"**Suggestion:** *{data.get('Title')}*\n\n"
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n\n\n"
        )
        
        # Get fun facts for the suggestion
        fun_facts = generate_ai_content(f"Give me some fun facts about the movie {movie_name}.")
        final_caption = details + fun_facts
        
        poster_url = data.get("Poster")
        
        # Buttons for suggestion (Download + Next)
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_btn = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_btn], [next_btn]])
        
        if poster_url and poster_url != "N/A":
            msg = await context.bot.send_photo(
                chat_id=CHAT_ID,
                photo=poster_url,
                caption=final_caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            msg = await context.bot.send_message(
                chat_id=CHAT_ID,
                text=final_caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        
        # Auto-delete after 5 minutes
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})

# Next button handler for suggestions
async def handle_suggest_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global suggestion_index
    trending_movies = get_trending_bollywood_movies()
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
    
    # Get movie details
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()
    
    if data.get("Response") == "True":
        details = (
            f"**Suggestion:** *{data.get('Title')}*\n\n"
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n\n\n"
        )
        
        fun_facts = generate_ai_content(f"Give me some fun facts about the movie {movie_name}.")
        final_caption = details + fun_facts
        poster_url = data.get("Poster")
        
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_btn = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_btn], [next_btn]])
        
        try:
            if poster_url and poster_url != "N/A":
                # Delete old message and send new one with photo
                await query.message.delete()
                new_msg = await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=poster_url,
                    caption=final_caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                context.job_queue.run_once(delete_bot_message, 300, data={"message": new_msg})
            else:
                # Edit existing message
                await query.edit_message_text(
                    text=final_caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Error in next button: {e}")

# AI response command
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question>😊")
        context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        return

    question = " ".join(context.args)
    ai_reply = generate_ai_content(question)
    message = await update.message.reply_text(ai_reply)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

# Main function
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern="^download_"))
    app.add_handler(CallbackQueryHandler(handle_suggest_next, pattern="^suggest_next"))
    
    # Schedule automated suggestions every 10 minutes
    app.job_queue.run_repeating(send_movie_suggestion, interval=600, first=10)

    # Run webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

# Entry point
if __name__ == "__main__":
    main()
