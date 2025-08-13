import os
import random
import logging
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

# ──────────────────── LOGGING ────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ────────────────────🔐 CONFIG ────────────────────
BOT_TOKEN           = os.getenv("BOT_TOKEN")
WEBHOOK_URL         = os.getenv("WEBHOOK_URL")
IMDB_API_KEY        = os.getenv("IMDB_API_KEY")
TMDB_API_KEY        = os.getenv("TMDB_API_KEY")
MONGO_URI           = os.getenv("MONGO_URI")
FRONTEND_URL        = "https://frontend-flyvio.vercel.app"
TUTORIAL_LINK       = "https://t.me/disneysworl_d"
WELCOME_IMAGE_URL   = "https://ar-hosting.pages.dev/1755088270275.png"
ADMIN_USERNAME      = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"
REDIRECTION_PREFIX  = "https://redirection2.vercel.app/?url="

# Parse multiple chat IDs from environment (comma separated)
TARGET_CHAT_IDS = [
    int(cid.strip())
    for cid in os.getenv("TARGET_CHAT_IDS", "-1001878181555,-1001955515603,-1001675134770").split(",")
    if cid.strip().isdigit()
]

# ──────────────────── DATABASE ────────────────────
client = MongoClient(MONGO_URI)
db      = client.get_default_database()
movies  = db["movie"]
tvshows = db["tv"]

# Memory for avoiding repeats
recently_posted_ids = []

# ──────────────────── HELPERS ────────────────────
def greeting():
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int):
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        for v in requests.get(url).json().get("results", []):
            if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception:
        logger.exception(f"Error getting trailer for TMDB {tmdb_id}")
    return None

def get_platforms(tmdb_id: int):
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        data = requests.get(url).json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception:
        logger.exception(f"Error getting platforms for TMDB {tmdb_id}")
        return []

def crop_16_9(url: str):
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
    except Exception:
        logger.exception(f"Error cropping image {url}")
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.job.data.get("msg").delete()
        logger.info("Auto-deleted message.")
    except:
        logger.warning("Failed to auto-delete message.")

def build_caption(info: dict, platforms: list[str]):
    try:
        title = info.get("Title") or info.get("title", "-")
        year = (info.get("Year") or info.get("release_date", "-"))[:4]
        rating = info.get("imdbRating") or info.get("vote_average", "-")
        genre = info.get("Genre") or ", ".join(g["name"] for g in info.get("genres", []))
        director = info.get("Director") or "-"
        plot = info.get("Plot") or info.get("overview", "-")
        cast = info.get("Actors") or "-"

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
    except Exception:
        logger.exception("Error building caption")
        return "Error generating caption."

def get_media_link(title: str):
    try:
        m = movies.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if m: return f"{FRONTEND_URL}/mov/{m['tmdb_id']}"
        t = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if t: return f"{FRONTEND_URL}/ser/{t['tmdb_id']}"
    except Exception:
        logger.exception(f"Error finding media link for {title}")
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str):
    try:
        rows = []
        if trailer:
            rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=REDIRECTION_PREFIX + trailer)])
        rows.append([
            InlineKeyboardButton("📥 720p HD", url=REDIRECTION_PREFIX + dl_link),
            InlineKeyboardButton("📥 1080p HD", url=REDIRECTION_PREFIX + dl_link),
        ])
        rows.append([InlineKeyboardButton("📚 Tutorial", url=TUTORIAL_LINK)])
        return InlineKeyboardMarkup(rows)
    except Exception:
        logger.exception("Error building buttons")
        return InlineKeyboardMarkup([])

# ──────────────────── PERIODIC JOB ────────────────────
async def send_latest_media_job(context: ContextTypes.DEFAULT_TYPE):
    global recently_posted_ids
    chat_id = context.job.chat_id
    try:
        latest_movies = list(movies.find().sort("uploaded_at", -1).limit(20))
        latest_tv = list(tvshows.find().sort("uploaded_at", -1).limit(20))
        combined = latest_movies + latest_tv
        if not combined:
            logger.warning("No media found in DB.")
            return

        candidates = [doc for doc in combined if str(doc["_id"]) not in recently_posted_ids]
        if not candidates:
            recently_posted_ids = []
            candidates = combined

        chosen = random.choice(candidates)
        recently_posted_ids.append(str(chosen["_id"]))
        if len(recently_posted_ids) > 50:
            recently_posted_ids = recently_posted_ids[-50:]

        tmdb_id = chosen.get("tmdb_id") or 0
        if chosen in latest_movies:
            details = requests.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
            ).json()
            trailer = get_trailer(tmdb_id)
            platforms = get_platforms(tmdb_id)
        else:
            details = requests.get(
                f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
            ).json()
            trailer = None
            platforms = []

        poster = f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None
        caption = build_caption(details, platforms)
        dl_link = get_media_link(details.get("title") or details.get("name") or "")
        buttons = build_buttons(trailer, dl_link)

        if poster:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=crop_16_9(poster),
                caption=caption,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )
        else:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )

        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        logger.info(f"Posted random media to chat {chat_id}")
    except Exception:
        logger.exception(f"Error posting to chat {chat_id}")

# ──────────────────── HANDLERS ────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.effective_user.first_name or "there"
        text = (
            f"{greeting()}, <b>{name}</b>! 🎬\n\n"
            "ɪ ᴀᴍ ᴍᴏᴠɪ-ʟ ᴡᴇʙsɪᴛᴇ ᴍᴀɴᴀɢᴇʀ ʙᴏᴛ,\n"
            "ᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ᴀɴᴅ sᴇᴇ ᴍᴀɢɪᴄ.\n\n"
            f"<i>ᴍᴀᴅᴇ ᴡɪᴛʜ ❤️ ʙʏ 𝗕𝗟𝗔𝗖𝗞 𝗘𝗠𝗣𝗘𝗥𝗢𝗥. "
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ᴛʀᴇɴᴅɪɴɢ ᴛᴏᴅᴀʏ", callback_data="trending")],
            [InlineKeyboardButton("ᴍᴏᴠɪ-ʟ ᴡᴇʙsɪᴛᴇ❤", url=f"https://redirection2.vercel.app/?url=https://frontend-flyvio.vercel.app/")]
        ])
        msg = await update.message.reply_photo(
            WELCOME_IMAGE_URL,
            caption=text,
            parse_mode=constants.ParseMode.HTML,
            reply_markup=buttons
        )
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
    except Exception:
        logger.exception("Error in /start")

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
    except Exception:
        logger.exception("Error in trending callback")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.message.text.strip()
        omdb = requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}").json()
        if omdb.get("Response") == "True":
            info = omdb
            trailer = None
            platforms = []
            poster = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
        else:
            search = requests.get(
                f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
            ).json().get("results", [])
            if not search:
                buttons = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔍 Try Google", url=f"https://www.google.com/search?q={query.replace(' ', '+')}")
                ]])
                msg = await update.message.reply_text(
                    "❗ Movie not found. Please check the spelling.",
                    parse_mode=constants.ParseMode.HTML,
                    reply_markup=buttons
                )
                context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
                return
            tmdb_id = search[0]["id"]
            info = requests.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
            ).json()
            trailer = get_trailer(tmdb_id)
            platforms = get_platforms(tmdb_id)
            poster = f"https://image.tmdb.org/t/p/w780{info.get('backdrop_path')}" if info.get("backdrop_path") else None

        caption = build_caption(info, platforms)
        dl_link = get_media_link(info.get("title") or info.get("Title", ""))
        buttons = build_buttons(trailer, dl_link)

        if poster:
            msg = await update.message.reply_photo(
                crop_16_9(poster),
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
    except Exception:
        logger.exception("Error in movie search")

# ──────────────────── MAIN ────────────────────
def main():
    try:
        logger.info("Starting bot...")
        app = Application.builder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))

        # Schedule 10-min job for each chat in TARGET_CHAT_IDS
        for cid in TARGET_CHAT_IDS:
            app.job_queue.run_repeating(send_latest_media_job, interval=600, first=10, chat_id=cid)
            logger.info(f"Scheduled 10min job for chat {cid}")

        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 10000)),
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    except Exception:
        logger.exception("Fatal error in main()")

if __name__ == "__main__":
    main()
