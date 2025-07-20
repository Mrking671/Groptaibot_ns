import os
import random
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from bs4 import BeautifulSoup
import difflib

# === ENVIRONMENT ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")

FREE_DOWNLOAD_LINK = "https://your-free-download-link.com"
PAID_DOWNLOAD_LINK = "https://your-paid-download-link.com"
CHAT_ID = int(os.getenv("CHAT_ID", "-1001878181555"))

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Global variable to track suggestion index
suggestion_index = 0

def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"Error generating AI response: {e}")
        return "Error generating AI response."

def get_ai_corrected_movie_name(incorrect_name: str) -> str:
    """Use AI to correct movie name spelling and get movie details"""
    try:
        prompt = f"""
        The user searched for a movie called "{incorrect_name}" but it was not found in the database.
        Please suggest the most likely correct movie title they were looking for.
        
        Respond in the following format:
        **[Corrected Movie Title]**
        
        Brief description: [2-3 sentences about the movie including genre, year if known, and main plot points]
        """
        
        response = model.generate_content(prompt)
        return response.text if response else f"**{incorrect_name}**\n\nSorry, could not find a correction for this movie name."
    except Exception as e:
        print(f"Error in AI correction: {e}")
        return f"**{incorrect_name}**\n\nError generating movie name correction."

async def delete_bot_message(context):
    data = context.job.data
    message = data.get("message")
    if message:
        try:
            await message.delete()
        except Exception:
            pass

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

def get_trending_bollywood_movies():
    url = "https://www.imdb.com/india/trending/"
    headers = {"User-Agent": "Mozilla/5.0"}
    movies = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ["Coolie", "War 2", "Kingdom"]
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup.select(".ipc-poster-card__title"):
            t = tag.get_text(strip=True)
            if t and t not in movies:
                movies.append(t)
    except Exception as e:
        print(f"Error fetching trending movies: {e}")
        movies = ["Coolie", "War 2", "Kingdom"]
    return movies or ["Coolie", "War 2", "Kingdom"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = f"{greeting}😊\n\nɪ'ᴍ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɪ ʙᴏᴛ ʜᴇʟᴘ ʏᴏᴜ ᴛᴏ ғɪɴᴅ ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴍᴏᴠɪᴇs ᴅᴇᴛᴀɪʟs.\nᴊᴜsᴛ ᴛʏᴘᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ʏᴏᴜ ᴍᴏᴠɪᴇ ᴅᴇᴛᴀɪʟs ᴀs ᴡᴇʟʟ ᴀs ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ.\n\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗.\n𝗠𝗔𝗗𝗘 𝗪𝗜𝗧𝗛 ❤ 𝗯𝘆 @Lordsakunaa"
    message = await update.message.reply_text(welcome_text)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        user_name = new_member.full_name or "Unknown User"
        user_id = new_member.id
        username = new_member.username or "No Username"
        try:
            photos = await context.bot.get_user_profile_photos(user_id)
            if photos.total_count > 0:
                photo_file = await context.bot.get_file(photos.photos[0][0].file_id)
                photo_bytes = await photo_file.download_as_bytearray()
                user_photo = Image.open(io.BytesIO(photo_bytes))
            else:
                user_photo = Image.new("RGB", (400, 400), (128, 128, 128))
        except Exception:
            user_photo = Image.new("RGB", (400, 400), (128, 128, 128))
        
        background = Image.new("RGB", (400, 400), "white")
        draw = ImageDraw.Draw(background)
        user_photo = user_photo.resize((300, 300)).convert("RGBA")
        mask = Image.new("L", user_photo.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + user_photo.size, fill=255)
        background.paste(user_photo, (50, 50), mask)
        
        try:
            font = ImageFont.truetype(random.choice(["arial.ttf", "times.ttf", "calibri.ttf"]), 24)
        except IOError:
            font = ImageFont.load_default()
        
        text_bbox = font.getbbox(user_name)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (400 - text_width) // 2
        draw.text((text_x, 350), user_name, fill="black", font=font, align="center")
        
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
        except Exception:
            pass

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question>😊")
        context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        return
    
    question = " ".join(context.args)
    ai_reply = generate_ai_content(question)
    message = await update.message.reply_text(ai_reply)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    movie_name = update.message.text.strip()
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()
    
    # If found exact match, show poster + details + fun fact + download button only
    if data.get("Response") == "True":
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
        fun_fact = generate_ai_content(f"Give me some fun facts about the movie {data.get('Title')}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
        
        # Only download button for exact match
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        keyboard = InlineKeyboardMarkup([[download_btn]])
        
        if poster_url and poster_url != "N/A":
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=final_caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            message = await update.message.reply_text(final_caption, parse_mode="Markdown", reply_markup=keyboard)
    
    else:
        # Movie not found - use AI to correct the name and provide details
        ai_correction_response = get_ai_corrected_movie_name(movie_name)
        
        message = await update.message.reply_text(
            ai_correction_response,
            parse_mode="Markdown"
        )
        
        # Show trending suggestions after AI correction
        trending = get_trending_bollywood_movies()
        suggestion_buttons = [[InlineKeyboardButton(m, callback_data=f"suggest_{m.replace(' ','_')}")] for m in trending[:3]]
        await update.message.reply_text(
            "🎬 **Trending Bollywood Movies:**",
            reply_markup=InlineKeyboardMarkup(suggestion_buttons),
            parse_mode="Markdown"
        )
    
    context.job_queue.run_once(delete_bot_message, 300, data={"message": update.message})

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_reply_markup(reply_markup=reply_markup)

async def send_movie_suggestion(context: ContextTypes.DEFAULT_TYPE):
    global suggestion_index
    
    trending_movies = get_trending_bollywood_movies()
    if not trending_movies:
        trending_movies = ["Coolie", "War 2", "Kingdom"]
    
    # Get movie for this suggestion
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
    
    # Get movie details
    resp = requests.get(f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}")
    data = resp.json()
    
    if data.get("Response") == "True":
        # Show "Suggestion:" in bold, then movie details with fun fact
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
        fun_fact = generate_ai_content(f"Give me some fun facts about the movie {movie_name}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
        
        # Download and Next buttons for suggestions
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
        
        # Auto-delete after 5 minutes (300 seconds)
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})
    else:
        # Fallback if movie not found
        msg = await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"**Suggestion:** *{movie_name}*\n\nSorry, details not available for this movie.",
            parse_mode="Markdown"
        )
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})

async def handle_suggest_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global suggestion_index
    trending_movies = get_trending_bollywood_movies()
    if not trending_movies:
        trending_movies = ["Coolie", "War 2", "Kingdom"]
    
    # Get next movie
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
    
    # Get movie details
    resp = requests.get(f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}")
    data = resp.json()
    
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
        fun_fact = generate_ai_content(f"Give me some fun facts about the movie {movie_name}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
        
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_btn = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_btn], [next_btn]])
        
        try:
            if poster_url and poster_url != "N/A":
                # Edit message with new photo and text
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
                # Edit text only
                await query.edit_message_text(
                    text=final_caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Error in next button: {e}")
    else:
        try:
            await query.edit_message_text(
                text=f"**Suggestion:** *{movie_name}*\n\nSorry, details not available for this movie.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error editing message: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern="^download_"))
    app.add_handler(CallbackQueryHandler(handle_suggest_next, pattern="^suggest_next"))
    
    # Send movie suggestion every 10 minutes
    app.job_queue.run_repeating(send_movie_suggestion, interval=600, first=10)
    
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
