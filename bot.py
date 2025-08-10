import os
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image
from pymongo import MongoClient

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ────────────────────🔐 CONFIG ────────────────────
BOT_TOKEN          = os.getenv("BOT_TOKEN")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL")
IMDB_API_KEY       = os.getenv("IMDB_API_KEY")
TMDB_API_KEY       = os.getenv("TMDB_API_KEY")
MONGO_URI          = os.getenv("MONGO_URI")
FRONTEND_URL       = "https://frontend-flyvio.vercel.app"
TUTORIAL_LINK      = "https://your-tutorial-url.com"  # Replace with your actual tutorial link
WELCOME_IMAGE_URL  = "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
ADMIN_USERNAME     = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"  # Change to your region code

# ──────────────────── DATABASE ────────────────────
client = MongoClient(MONGO_URI)
db      = client.get_default_database()
movies  = db["movie"]
tvshows = db["tv"]

# ──────────────────── HELPERS ────────────────────
def greeting() -> str:
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int) -> str | None:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
    for v in requests.get(url).json().get("results", []):
        if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
            return f"https://www.youtube.com/watch?v={v['key']}"
    return None

def get_platforms(tmdb_id: int) -> list[str]:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
    data = requests.get(url).json().get("results", {}).get(DEFAULT_REGION, {})
    return [p["provider_name"] for p in data.get("flatrate", [])]

def crop_16_9(url: str) -> BytesIO | str:
    try:
        img = Image.open(BytesIO(requests.get(url).content))
        w, h = img.size
        nh = int(w * 9 / 16)
        if h > nh:
            top = (h - nh) // 2
            img = img.crop((0, top, w, top + nh))
        buf = BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        return buf
    except:
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        await msg.delete()
    except:
        pass

def build_caption(info: dict, platforms: list[str]) -> str:
    title    = info.get("Title") or info.get("title", "-")
    year     = (info.get("Year") or info.get("release_date", "-"))[:4]
    rating   = info.get("imdbRating") or info.get("vote_average", "-")
    genre    = info.get("Genre") or ", ".join(g["name"] for g in info.get("genres", []))
    director = info.get("Director") or "-"
    plot     = info.get("Plot") or info.get("overview", "-")
    cast     = info.get("Actors") or "-"

    caption = (
        f"🎬 <b><u>{title.upper()}</u></b>\n"
        f"┏━━━━━━━━━━━━━━━━━━\n"
        f"┃ <b>Year:</b> {year}\n"
        f"┃ <b>IMDb:</b> ⭐ {rating}\n"
        f"┃ <b>Genre:</b> {genre}\n"
        f"┃ <b>Director:</b> {director}\n"
        f"┗━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📝 Plot:</b>\n<em>{plot}</em>\n"
    )
    if cast != "-":
        caption += f"\n<b>🎞️ Cast:</b> {cast}\n"
    if platforms:
        caption += f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"
    return caption

def get_media_link(title: str) -> str:
    """Return a frontend URL based on MongoDB match; otherwise base URL."""
    # exact (case-insensitive) title match in movies
    doc = movies.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
    if doc:
        return f"{FRONTEND_URL}/mov/{doc['tmdb_id']}"
    # check tv collection
    doc = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
    if doc:
        return f"{FRONTEND_URL}/ser/{doc['tmdb_id']}"
    # fallback
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if trailer:
        rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=trailer)])
    rows.append([
        InlineKeyboardButton("📥 720p HD", url=dl_link),
        InlineKeyboardButton("📥 1080p HD", url=dl_link),
    ])
    rows.append([InlineKeyboardButton("📚 Tutorial", url=TUTORIAL_LINK)])
    return InlineKeyboardMarkup(rows)

# ──────────────────── HANDLERS ────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    text = (
        f"{greeting()}, <b>{name}</b>! 🎬\n\n"
        "I’m your AI Movie Assistant. Send a movie title to get details,\n"
        "trailers, streaming platforms & download links.\n\n"
        f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 ᴛʀᴇɴᴅɪɴɢ", callback_data="trending")],
        [InlineKeyboardButton("👤 ʜᴇʟᴘ", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    msg = await update.message.reply_photo(
        WELCOME_IMAGE_URL,
        caption=text,
        parse_mode=constants.ParseMode.HTML,
        reply_markup=buttons
    )
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    results = requests.get(
        f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
    ).json().get("results", [])[:5]
    text = "<b>🔥 Trending Movies:</b>\n\n"
    for i, m in enumerate(results, start=1):
        text += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
    msg = await update.callback_query.message.reply_text(text, parse_mode=constants.ParseMode.HTML)
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    # Try IMDb via OMDb
    omdb = requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}").json()
    if omdb.get("Response") == "True":
        info      = omdb
        tmdb_id   = None
        trailer   = None
        platforms = []
        poster    = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
    else:
        # Fallback to TMDb
        search = requests.get(
            f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
        ).json().get("results", [])
        if not search:
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔍 Try Google",
                    url=f"https://www.google.com/search?q={query.replace(' ', '+')}"
                )
            ]])
            msg = await update.message.reply_text(
                "❗ Movie not found. Please check the spelling.",
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )
            context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
            return

        tmdb_id   = search[0]["id"]
        details   = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            f"?api_key={TMDB_API_KEY}&append_to_response=credits"
        ).json()
        trailer   = get_trailer(tmdb_id)
        platforms = get_platforms(tmdb_id)
        info      = details
        poster    = (
            f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}"
            if details.get("backdrop_path") else None
        )

    caption = build_caption(info, platforms)
    dl_link = get_media_link(info.get("title") or info.get("Title", ""))
    buttons = build_buttons(trailer, dl_link)

    if poster:
        img_msg = crop_16_9(poster)
        msg = await update.message.reply_photo(
            img_msg,
            caption=caption,
            parse_mode=constants.ParseMode.HTML,
            reply_markup=buttons
        )
    else:
        msg = await update.message.reply_text(
            caption,
            parse_mode=constants.ParseMode.HTML,
            reply_markup=buttons
        )

    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})

# ──────────────────── MAIN ────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
