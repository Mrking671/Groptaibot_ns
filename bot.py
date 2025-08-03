import os
import requests
import google.generativeai as genai
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)
from datetime import datetime
from PIL import Image
from io import BytesIO

# -----------------🔐 CONFIG ----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Replace these with your data
WELCOME_IMAGE_URL = "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
SERVER1_LINK = "https://movii-l.vercel.app/"
SERVER2_LINK = "https://movi-l.netlify.app/"
ADMIN_USERNAME = "Lordsakunaa"

AUTO_DELETE_SECONDS = 100
DEFAULT_REGION = "IN"  # Use "US" for United States, etc.

# -----------------🧠 MODELS ----------------------
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# -----------------💬  UTILITIES ----------------------
def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Good morning"
    elif 12 <= hour < 18: return "Good afternoon"
    elif 18 <= hour < 22: return "Good evening"
    else: return "Good night"

def get_trailer_url(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
    res = requests.get(url).json()
    for vid in res.get('results', []):
        if vid['type'].lower() == "trailer" and vid['site'].lower() == "youtube":
            return f"https://www.youtube.com/watch?v={vid['key']}"
    return None

def get_streaming_platforms(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={TMDB_API_KEY}"
    res = requests.get(url).json()
    platforms = res.get('results', {}).get(DEFAULT_REGION, {}).get('flatrate', [])
    if platforms:
        return [p['provider_name'] for p in platforms]
    return []

def create_buttons(trailer_url):
    buttons = []
    if trailer_url:
        buttons.append([InlineKeyboardButton("▶️ Watch Trailer", url=trailer_url)])
    download_row = [
        InlineKeyboardButton("📥 Server 1", url=SERVER1_LINK),
        InlineKeyboardButton("📥 Server 2", url=SERVER2_LINK)
    ]
    buttons.append(download_row)
    return InlineKeyboardMarkup(buttons)

def stylized_movie_ui(data: dict, platforms: list):
    title = data.get("Title") or data.get("title") or "-"
    year = data.get("Year") or data.get("release_date", "-")[:4]
    rating = data.get("imdbRating") or data.get("vote_average", '-')
    genre = data.get("Genre") or ", ".join([g.get("name") for g in data.get("genres", [])])
    director = data.get("Director") or "-"
    plot = data.get("Plot") or data.get("overview", "-")
    cast = data.get("Actors") or "-"
    
    msg = (
        f"🎬 <b><u>{title.upper()}</u></b>\n"
        f"┏━━━━━━━━━━━━━━━━━━\n"
        f"┃ <b>Year:</b> {year}\n"
        f"┃ <b>IMDb:</b> ⭐ {rating}\n"
        f"┃ <b>Genre:</b> {genre}\n"
        f"┃ <b>Director:</b> {director}\n"
        f"┗━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📝 Plot:</b>\n<em>{plot}</em>\n"
    )

    if cast and cast != "-":
        msg += f"\n<b>🎞️ Cast:</b> {cast}\n"

    if platforms:
        msg += f"\n<b>📺 Streaming On:</b> {', '.join(platforms)}"

    return msg

def delete_message_later(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    message = job_data.get("message")
    try:
        if message:
            message.delete()
    except Exception:
        pass

# -----------------🤖 HANDLERS ----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    greet = get_greeting()
    name = user.first_name or "there"

    text = (
        f"{greet}, <b>{name}</b>! 🎬\n\n"
        f"I'm your AI Movie Assistant 👋 Find movies, trailers, platforms and links instantly!\n\n"
        f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trending Movies", callback_data="trending_movies")],
        [InlineKeyboardButton("📥 Download Server 1", url=SERVER1_LINK)],
        [InlineKeyboardButton("📥 Download Server 2", url=SERVER2_LINK)],
        [InlineKeyboardButton("👤 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    msg = await update.message.reply_photo(WELCOME_IMAGE_URL, caption=text, parse_mode="HTML", reply_markup=buttons)
    context.job_queue.run_once(delete_message_later, AUTO_DELETE_SECONDS, data={"message": msg})

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Step 1: Try IMDb (OMDb)
    omdb_url = f"http://www.omdbapi.com/?t={text}&apikey={IMDB_API_KEY}"
    omdb_data = requests.get(omdb_url).json()
    if omdb_data.get("Response") == "True":
        msg = stylized_movie_ui(omdb_data, [])
        poster = omdb_data.get("Poster")
        kb = create_buttons(None)
    else:
        # Step 2: Fallback to TMDb
        search = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={text}"
        res = requests.get(search).json().get("results", [])
        if not res:
            msg = "❗ Movie not found.\nPlease check your spelling.\nYou can try Google search:"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Search Google", url=f"https://www.google.com/search?q={text}")]
            ])
            m = await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
            context.job_queue.run_once(delete_message_later, AUTO_DELETE_SECONDS, data={"message": m})
            return

        mid = res[0].get("id")
        details = requests.get(f"https://api.themoviedb.org/3/movie/{mid}?api_key={TMDB_API_KEY}&append_to_response=credits").json()
        trailer_url = get_trailer_url(mid)
        platforms = get_streaming_platforms(mid)
        msg = stylized_movie_ui(details, platforms)
        poster = f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None
        kb = create_buttons(trailer_url)

    if poster and poster != "N/A":
        try:
            img = BytesIO(requests.get(poster).content)
            m = await update.message.reply_photo(photo=img, caption=msg, parse_mode="HTML", reply_markup=kb)
        except:
            m = await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    else:
        m = await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

    context.job_queue.run_once(delete_message_later, AUTO_DELETE_SECONDS, data={"message": m})

async def trending_movies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
    data = requests.get(url).json()
    results = data.get("results", [])[:5]
    text = "<b>🔥 Trending Today:</b>\n"
    for i, movie in enumerate(results, 1):
        title = movie.get("title")
        year = movie.get("release_date", "")[:4]
        text += f"<b>{i}.</b> {title} ({year})\n"
    msg = await query.message.reply_text(text, parse_mode="HTML")
    context.job_queue.run_once(delete_message_later, AUTO_DELETE_SECONDS, data={"message": msg})

# -----------------🚀 MAIN ----------------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(trending_movies_callback, pattern="^trending_movies$"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
          
