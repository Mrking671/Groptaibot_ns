import os
import random
import requests
import logging
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

# ─────────────── Logging & Error Handling ───────────────
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ────────────────────🔐 CONFIG ────────────────────
BOT_TOKEN          = os.getenv("BOT_TOKEN")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL")
IMDB_API_KEY       = os.getenv("IMDB_API_KEY")
TMDB_API_KEY       = os.getenv("TMDB_API_KEY")
MONGO_URI          = os.getenv("MONGO_URI")
FRONTEND_URL       = "https://frontend-flyvio.vercel.app"
TUTORIAL_LINK      = "https://t.me/disneysworl_d"  # Replace with your actual tutorial link
WELCOME_IMAGE_URL  = "https://ar-hosting.pages.dev/1742397369670.jpg"
ADMIN_USERNAME     = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"  # Change to your region code

# Add your multiple target chat IDs here
TARGET_CHAT_IDS = [
    -1001878181555,
    -1001675134770,
    -1001955515603,
]

# Add your broadcast channel ID here
BROADCAST_CHANNEL_ID = -1002097771669  # Replace with your channel's actual ID

# ──────────────────── DATABASE ────────────────────
client = MongoClient(MONGO_URI)
db      = client.get_default_database()
movies  = db["movie"]
tvshows = db["tv"]

# To track posted movie IDs and avoid repetition
posted_movie_ids = set()

# ──────────────────── HELPERS ────────────────────
def greeting() -> str:
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int) -> str | None:
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        for v in requests.get(url).json().get("results", []):
            if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception as e:
        logger.error(f"Error fetching trailer for TMDB ID {tmdb_id}: {e}")
    return None

def get_platforms(tmdb_id: int) -> list[str]:
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        data = requests.get(url).json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception as e:
        logger.error(f"Error fetching platforms for TMDB ID {tmdb_id}: {e}")
    return []

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
    except Exception as e:
        logger.error(f"Image crop failed for URL {url}: {e}")
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        await msg.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")

def build_caption(info: dict, platforms: list[str]) -> str:
    title    = info.get("Title") or info.get("title", "-")
    year     = (info.get("Year") or info.get("release_date", "-"))[:4]
    rating   = info.get("imdbRating") or info.get("vote_average", "-")
    # Robust genre handling:
    genre = "-"
    if info.get("Genre"):
        genre = info.get("Genre")
    elif isinstance(info.get("genres", None), list):
        genres = info["genres"]
        if all(isinstance(g, dict) and "name" in g for g in genres):
            genre = ", ".join(g["name"] for g in genres)
        elif all(isinstance(g, str) for g in genres):
            genre = ", ".join(genres)
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
    try:
        doc = movies.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if doc:
            return f"{FRONTEND_URL}/mov/{doc['tmdb_id']}"
        doc = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if doc:
            return f"{FRONTEND_URL}/ser/{doc['tmdb_id']}"
    except Exception as e:
        logger.error(f"Error getting media link for {title}: {e}")
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str) -> InlineKeyboardMarkup:
    redirect = lambda url: f"https://redirection2.vercel.app/?url={url}"
    rows: list[list[InlineKeyboardButton]] = []
    if trailer:
        rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=redirect(trailer))])
    rows.append([
        InlineKeyboardButton("📥 720p HD", url=redirect(dl_link)),
        InlineKeyboardButton("📥 1080p HD", url=redirect(dl_link)),
    ])
    # Tutorial button WITHOUT redirection
    rows.append([InlineKeyboardButton("📚 Tutorial", url=TUTORIAL_LINK)])
    return InlineKeyboardMarkup(rows)

# ──────────────────── HANDLERS ────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception during handling update: {context.error}", exc_info=context.error)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.effective_user.first_name or "there"
        text = (
            f"{greeting()}, <b>{name}</b>! 🎬\n\n"
            "ᴡᴇʟᴄᴏᴍᴇ 🎉 ᴛᴏ ᴍᴏᴠɪ-ʟ ᴡᴇʙsɪᴛᴇ ᴏғғɪᴄɪᴀʟ ʙᴏᴛ,\n"
            "ᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ᴀɴᴅ sᴇᴇ ᴍᴀɢɪᴄ.\n\n"
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
    except Exception as e:
        logger.error(f"Error in start handler: {e}")

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
        results = requests.get(
            f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
        ).json().get("results", [])[:5]
        text = "<b>🔥 Trending Movies:</b>\n\n"
        for i, m in enumerate(results, start=1):
            text += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
        msg = await update.callback_query.message.reply_text(text, parse_mode=constants.ParseMode.HTML)
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
    except Exception as e:
        logger.error(f"Error in trending callback: {e}")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            logger.warning(f"Received update without message text: {update}")
            return
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
    except Exception as e:
        logger.error(f"Error in movie_search handler: {e}")

# ──────────────────── ADD MOVIE TO BROADCAST CHANNEL ────────────────────
async def add_movie_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❗ Please specify a movie name after /add.")
            return

        query = " ".join(context.args)

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
                await update.message.reply_text("❗ Movie not found. Please check the spelling.")
                return

            tmdb_id   = search[0]["id"]
            details   = requests.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
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

        # Send to broadcast channel (do NOT auto-delete!)
        if poster:
            img_msg = crop_16_9(poster)
            await context.bot.send_photo(
                BROADCAST_CHANNEL_ID,
                img_msg,
                caption=caption,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )
        else:
            await context.bot.send_message(
                BROADCAST_CHANNEL_ID,
                caption,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )

        await update.message.reply_text(f"✅ Movie broadcasted to the channel.")
    except Exception as e:
        logger.error(f"Error in add_movie_broadcast handler: {e}")

# ──────────────────── AUTO-POST JOB ────────────────────
AUTO_POST_INTERVAL = 600  # 10 minutes in seconds

async def auto_post_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        global posted_movie_ids

        # Total number of movies in collection
        count = movies.count_documents({})
        if count == 0:
            logger.warning("No movies available for auto-post.")
            return

        # Filter to exclude already posted movies
        filter_query = {"_id": {"$nin": list(posted_movie_ids)}} if posted_movie_ids else {}

        # Sample a random movie not posted yet
        pipeline = [
            {"$match": filter_query},
            {"$sample": {"size": 1}}
        ]
        movie_list = list(movies.aggregate(pipeline))

        if not movie_list:
            posted_movie_ids.clear()
            movie_list = list(movies.aggregate([{"$sample": {"size": 1}}]))

        if not movie_list:
            logger.warning("No movies found to post after reset.")
            return

        movie = movie_list[0]
        posted_movie_ids.add(movie["_id"])

        tmdb_id = movie.get("tmdb_id")
        trailer = get_trailer(tmdb_id) if tmdb_id else None
        platforms = get_platforms(tmdb_id) if tmdb_id else []
        caption = build_caption(movie, platforms)
        dl_link = get_media_link(movie.get("title", ""))
        buttons = build_buttons(trailer, dl_link)
        poster_url = f"https://image.tmdb.org/t/p/w780{movie.get('backdrop_path')}" if movie.get("backdrop_path") else None

        for chat_id in TARGET_CHAT_IDS:
            try:
                if poster_url:
                    img_msg = crop_16_9(poster_url)
                    msg = await context.bot.send_photo(
                        chat_id,
                        img_msg,
                        caption=caption,
                        parse_mode=constants.ParseMode.HTML,
                        reply_markup=buttons
                    )
                else:
                    msg = await context.bot.send_message(
                        chat_id,
                        caption,
                        parse_mode=constants.ParseMode.HTML,
                        reply_markup=buttons
                    )
                context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
            except Exception as e:
                logger.error(f"Failed auto-post in chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Error in auto_post_job: {e}")

# ──────────────────── MAIN ────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.add_handler(CommandHandler("add", add_movie_broadcast))

    # Add error handler
    app.add_error_handler(error_handler)

    # Schedule auto-post every 10 minutes, starting after 10 seconds
    app.job_queue.run_repeating(auto_post_job, interval=AUTO_POST_INTERVAL, first=10)

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
    
