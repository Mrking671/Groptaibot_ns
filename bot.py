import os
import random
import requests
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from bs4 import BeautifulSoup
import difflib

# Set Gemini API Key directly here
GEMINI_API_KEY = "AIzaSyAt26gU1ZOOuy5atbSOAzrfrpIfSuFvnnY"
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # or your key
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Set your Telegram bot token!
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHAT_ID = int(os.getenv("CHAT_ID", "-1001234567890"))  # For suggestions

FREE_DOWNLOAD_LINK = "https://your-free-download-link.com"
PAID_DOWNLOAD_LINK = "https://your-paid-download-link.com"

# --- Gemini Client ---
client = genai.Client(api_key=GEMINI_API_KEY)

def gemini_complete(prompt: str) -> str:
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return getattr(response, "text", None) or getattr(response, "result", None) or str(response)
    except Exception as e:
        print(f"Gemini API error: {e}")
        return "AI error: Could not fetch a response at this time."

async def delete_bot_message(context):
    data = context.job.data
    m = data.get("message")
    if m:
        try:
            await m.delete()
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
        print(f"Trending fetch error: {e}")
        movies = ["Coolie", "War 2", "Kingdom"]
    return movies or ["Coolie", "War 2", "Kingdom"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    text = f"""{greeting}😊

ɪ'ᴍ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɪ ʙᴏᴛ ʜᴇʟᴘ ʏᴏᴜ ᴛᴏ ғɪɴᴅ ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴍᴏᴠɪᴇs ᴅᴇᴛᴀɪʟs.
ᴊᴜsᴛ ᴛʏᴘᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ʏᴏᴜ ᴍᴏᴠɪᴇ ᴅᴇᴛᴀɪʟs ᴀs ᴡᴇʟʟ ᴀs ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ.

ᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗.
𝗠𝗔𝗗𝗘 𝗪𝗜𝗧𝗛 ❤ 𝗯𝘆 @Lordsakunaa"""
    m = await update.message.reply_text(text)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": m})

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
            font = ImageFont.truetype(random.choice(
                ["arial.ttf", "times.ttf", "calibri.ttf"]), 24)
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
            m = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=output,
                caption=f"𝐖𝐄𝐋𝐂𝐎𝐌𝐄❤\n\n👤 Name: {user_name}\n🆔 ID: {user_id}\n🔗 Username: @{username}\n\nᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ɪᴛ ᴛᴏ ʏᴏᴜ😊\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗"
            )
            context.job_queue.run_once(delete_bot_message, 100, data={"message": m})
        except Exception:
            pass

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        m = await update.message.reply_text("Please provide a question. Usage: /ai <your question>😊")
        context.job_queue.run_once(delete_bot_message, 100, data={"message": m})
        return
    q = " ".join(context.args)
    ai_reply = gemini_complete(q)
    m = await update.message.reply_text(ai_reply)
    context.job_queue.run_once(delete_bot_message, 100, data={"message": m})

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    movie_name = update.message.text.strip()
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()
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
        fun_fact = gemini_complete(f"Give me some fun facts about the movie {data.get('Title')}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        keyboard = InlineKeyboardMarkup([[download_btn]])
        if poster_url and poster_url != "N/A":
            m = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=final_caption,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            m = await update.message.reply_text(final_caption, parse_mode="Markdown", reply_markup=keyboard)
    else:
        # --- AI Correction ---
        trending = get_trending_bollywood_movies()
        close = difflib.get_close_matches(movie_name, trending, n=1, cutoff=0.6)
        ai_text = None
        if close:
            corrected = close[0]
            imdb_url = f"http://www.omdbapi.com/?t={corrected}&apikey={IMDB_API_KEY}"
            data2 = requests.get(imdb_url).json()
            if data2.get("Response") == "True":
                ai_text = (
                    f"**{data2.get('Title', corrected)}**\n"
                    f"🎬 *Title*: {data2.get('Title', '-')}\n"
                    f"📅 *Year*: {data2.get('Year', '-')}\n"
                    f"⭐ *IMDb Rating*: {data2.get('imdbRating', '-')}\n"
                    f"🎭 *Genre*: {data2.get('Genre', '-')}\n"
                    f"📝 *Plot*: {data2.get('Plot', '-')}\n\n"
                    f"{gemini_complete(f'In 2 lines, tell about {data2.get(\"Title\", corrected)}')}"
                )
            else:
                ai_text = None
        if not ai_text:
            prompt = (
                f"The user searched for a movie called '{movie_name}'. "
                "Suggest the most likely correct movie name in bold Markdown, and below it, provide a few details (year, genre, summary) if possible."
            )
            ai_text = gemini_complete(prompt)
        m = await update.message.reply_text(ai_text, parse_mode="Markdown")
        suggestions = get_trending_bollywood_movies()
        btns = [[InlineKeyboardButton(m, callback_data=f"suggest_{m.replace(' ','_')}")]
                for m in suggestions[:3]]
        await update.message.reply_text("Trending Bollywood Movies:", reply_markup=InlineKeyboardMarkup(btns))
    context.job_queue.run_once(delete_bot_message, 300, data={"message": update.message})

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [InlineKeyboardButton("🆓 Free", url=FREE_DOWNLOAD_LINK)],
        [InlineKeyboardButton("💎 Paid", url=PAID_DOWNLOAD_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await q.edit_message_reply_markup(reply_markup=reply_markup)

suggestion_index = 0
async def send_movie_suggestion(context: ContextTypes.DEFAULT_TYPE):
    global suggestion_index
    trending_movies = get_trending_bollywood_movies()
    if not trending_movies:
        trending_movies = ["Coolie", "War 2", "Kingdom"]
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
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
        fun_fact = gemini_complete(f"Give me some fun facts about the movie {movie_name}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
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
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})
    else:
        msg = await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"**Suggestion:** *{movie_name}*\n\nSorry, details not available for this movie.",
            parse_mode="Markdown"
        )
        context.job_queue.run_once(delete_bot_message, 300, data={"message": msg})

async def handle_suggest_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    global suggestion_index
    trending_movies = get_trending_bollywood_movies()
    if not trending_movies:
        trending_movies = ["Coolie", "War 2", "Kingdom"]
    movie_name = trending_movies[suggestion_index % len(trending_movies)]
    suggestion_index = (suggestion_index + 1) % len(trending_movies)
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
        fun_fact = gemini_complete(f"Give me some fun facts about the movie {movie_name}.")
        poster_url = data.get("Poster")
        final_caption = details + (fun_fact or "")
        download_btn = InlineKeyboardButton("📥 Download", callback_data=f"download_{data.get('imdbID', 'unknown')}")
        next_btn = InlineKeyboardButton("➡️ Next", callback_data="suggest_next")
        keyboard = InlineKeyboardMarkup([[download_btn], [next_btn]])
        try:
            if poster_url and poster_url != "N/A":
                await q.message.delete()
                new_msg = await context.bot.send_photo(
                    chat_id=q.message.chat_id,
                    photo=poster_url,
                    caption=final_caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                context.job_queue.run_once(delete_bot_message, 300, data={"message": new_msg})
            else:
                await q.edit_message_text(
                    text=final_caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        except Exception as e:
            print(f"Error in next button: {e}")
    else:
        try:
            await q.edit_message_text(
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
    app.job_queue.run_repeating(send_movie_suggestion, interval=600, first=10)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
