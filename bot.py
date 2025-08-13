import os
import random
import logging
import requests
import html
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
TUTORIAL_LINK       = "https://your-tutorial-url.com"
WELCOME_IMAGE_URL   = "https://i.postimg.cc/t4cV2Hnz/image-4.png"
ADMIN_USERNAME      = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"
REDIRECTION_PREFIX  = "https://redirection2.vercel.app/?url="

# Target channel IDs for 10-minute posts
TARGET_CHAT_IDS = [-1001878181555, -1001675134770, -1001955515603]

# ──────────────────── DATABASE ────────────────────
try:
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    movies = db["movie"]
    tvshows = db["tv"]
    logger.info("Connected to MongoDB successfully")
except Exception as e:
    logger.exception("Failed to connect to MongoDB")
    movies = None
    tvshows = None

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
        if not tmdb_id or not TMDB_API_KEY:
            return None
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        response = requests.get(url, timeout=10)
        for v in response.json().get("results", []):
            if v.get("site", "").lower() == "youtube" and v.get("type", "").lower() == "trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception:
        logger.exception(f"Error getting trailer for TMDB {tmdb_id}")
    return None

def get_platforms(tmdb_id: int):
    try:
        if not tmdb_id or not TMDB_API_KEY:
            return []
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        response = requests.get(url, timeout=10)
        data = response.json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception:
        logger.exception(f"Error getting platforms for TMDB {tmdb_id}")
        return []

def crop_16_9(url: str):
    try:
        response = requests.get(url, timeout=10)
        img = Image.open(BytesIO(response.content))
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
        msg = context.job.data.get("msg")
        if msg:
            await msg.delete()
            logger.info("Auto-deleted message successfully")
    except Exception:
        logger.warning("Failed to auto-delete message")

def build_caption(info: dict, platforms: list[str]):
    try:
        # Safely get and escape all text fields
        title = html.escape(str(info.get("Title") or info.get("title") or "Unknown Title"))
        year = str(info.get("Year") or info.get("release_date") or "Unknown")[:4]
        rating = str(info.get("imdbRating") or info.get("vote_average") or "N/A")
        
        # Handle genre field safely
        if info.get("Genre"):
            genre = html.escape(str(info.get("Genre")))
        elif info.get("genres"):
            genre = ", ".join(html.escape(g.get("name", "")) for g in info.get("genres", []))
        else:
            genre = "Unknown"
            
        director = html.escape(str(info.get("Director") or "Unknown"))
        plot = html.escape(str(info.get("Plot") or info.get("overview") or "No plot available"))
        cast = html.escape(str(info.get("Actors") or "Unknown"))

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
        
        if cast and cast != "Unknown":
            caption += f"\n<b>🎞️ Cast:</b> {cast}\n"
        if platforms:
            platform_list = ", ".join(html.escape(str(p)) for p in platforms)
            caption += f"\n<b>📺 Streaming on:</b> {platform_list}"
        
        return caption
    except Exception:
        logger.exception("Error building caption")
        return "🎬 <b>Movie Information</b>\n\nError generating details."

def get_media_link(title: str):
    try:
        if not movies or not tvshows or not title:
            return FRONTEND_URL
            
        # Search in movies collection
        movie_doc = movies.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if movie_doc and movie_doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/mov/{movie_doc['tmdb_id']}"
            
        # Search in TV shows collection
        tv_doc = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if tv_doc and tv_doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/ser/{tv_doc['tmdb_id']}"
            
    except Exception:
        logger.exception(f"Error finding media link for {title}")
    return FRONTEND_URL

def build_buttons(trailer: str, dl_link: str):
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
        return InlineKeyboardMarkup([[InlineKeyboardButton("📚 Tutorial", url=TUTORIAL_LINK)]])

# ──────────────────── PERIODIC JOB ────────────────────
async def send_latest_media_job(context: ContextTypes.DEFAULT_TYPE):
    global recently_posted_ids
    chat_id = context.job.chat_id
    
    try:
        if not movies or not tvshows:
            logger.error("Database collections not available")
            return

        # Get latest media from both collections
        latest_movies = list(movies.find().sort("uploaded_at", -1).limit(20))
        latest_tv = list(tvshows.find().sort("uploaded_at", -1).limit(20))
        combined = latest_movies + latest_tv
        
        if not combined:
            logger.warning("No media found in database")
            return

        # Filter out recently posted
        candidates = [doc for doc in combined if str(doc.get("_id")) not in recently_posted_ids]
        if not candidates:
            recently_posted_ids = []
            candidates = combined

        chosen = random.choice(candidates)
        recently_posted_ids.append(str(chosen.get("_id")))
        
        # Keep list manageable
        if len(recently_posted_ids) > 50:
            recently_posted_ids = recently_posted_ids[-50:]

        tmdb_id = chosen.get("tmdb_id")
        if not tmdb_id:
            logger.warning("No TMDB ID found for chosen media")
            return

        # Determine if it's a movie or TV show and fetch details
        is_movie = chosen in latest_movies
        
        if is_movie:
            api_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
        else:
            api_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"

        response = requests.get(api_url, timeout=15)
        details = response.json()
        
        # Get additional info
        trailer = get_trailer(tmdb_id) if is_movie else None
        platforms = get_platforms(tmdb_id) if is_movie else []
        
        # Build poster URL
        poster = None
        if details.get("backdrop_path"):
            poster = f"https://image.tmdb.org/t/p/w780{details['backdrop_path']}"
        elif details.get("poster_path"):
            poster = f"https://image.tmdb.org/t/p/w780{details['poster_path']}"

        # Build message
        caption = build_caption(details, platforms)
        title = details.get("title") or details.get("name") or chosen.get("title", "")
        dl_link = get_media_link(title)
        buttons = build_buttons(trailer, dl_link)

        # Send message
        if poster:
            try:
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=crop_16_9(poster),
                    caption=caption,
                    parse_mode=constants.ParseMode.HTML,
                    reply_markup=buttons
                )
            except Exception:
                # Fallback to text message if photo fails
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
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

        # Schedule deletion
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        logger.info(f"Posted media '{title}' to chat {chat_id}")
        
    except Exception:
        logger.exception(f"Error in periodic job for chat {chat_id}")

# ──────────────────── HANDLERS ────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        name = user.first_name if user else "there"
        
        text = (
            f"{greeting()}, <b>{html.escape(name)}</b>! 🎬\n\n"
            "I'm your AI Movie Assistant. Send a movie title to get details,\n"
            "trailers, streaming platforms & download links.\n\n"
            f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}"
        )
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ᴛʀᴇɴᴅɪɴɢ", callback_data="trending")],
            [InlineKeyboardButton("👤 ʜᴇʟᴘ", url=f"https://t.me/{ADMIN_USERNAME}")]
        ])

        # Handle different update types
        if update.message:
            msg = await update.message.reply_photo(
                photo=WELCOME_IMAGE_URL,
                caption=text,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )
        elif update.effective_chat:
            msg = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=WELCOME_IMAGE_URL,
                caption=text,
                parse_mode=constants.ParseMode.HTML,
                reply_markup=buttons
            )
        else:
            logger.warning("No valid chat context for /start command")
            return

        # Schedule deletion
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        logger.info(f"Sent /start message to user {name}")
        
    except Exception:
        logger.exception("Error in /start handler")
        # Fallback text message
        try:
            fallback_text = f"{greeting()}! 🎬\n\nI'm your AI Movie Assistant. Send a movie title to get details!"
            if update.message:
                await update.message.reply_text(fallback_text)
            elif update.effective_chat:
                await context.bot.send_message(update.effective_chat.id, fallback_text)
        except Exception:
            logger.exception("Failed to send fallback start message")

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
        
        if not TMDB_API_KEY:
            await update.callback_query.message.reply_text("API key not configured.")
            return
            
        response = requests.get(
            f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}",
            timeout=10
        )
        results = response.json().get("results", [])[:5]
        
        text = "<b>🔥 Trending Movies:</b>\n\n"
        for i, movie in enumerate(results, start=1):
            title = html.escape(movie.get("title", "Unknown"))
            year = movie.get("release_date", "")[:4] if movie.get("release_date") else "Unknown"
            text += f"<b>{i}.</b> {title} ({year})\n"
        
        msg = await update.callback_query.message.reply_text(
            text, 
            parse_mode=constants.ParseMode.HTML
        )
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        
    except Exception:
        logger.exception("Error in trending callback")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text:
            return
            
        query = update.message.text.strip()
        if not query:
            return

        info = None
        trailer = None
        platforms = []
        poster = None

        # Try OMDB first
        if IMDB_API_KEY:
            try:
                omdb_response = requests.get(
                    f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",
                    timeout=10
                )
                omdb = omdb_response.json()
                if omdb.get("Response") == "True":
                    info = omdb
                    poster = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
            except Exception:
                logger.warning("OMDB API request failed")

        # Fallback to TMDB
        if not info and TMDB_API_KEY:
            try:
                search_response = requests.get(
                    f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}",
                    timeout=10
                )
                search_results = search_response.json().get("results", [])
                
                if search_results:
                    tmdb_id = search_results[0]["id"]
                    details_response = requests.get(
                        f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits",
                        timeout=15
                    )
                    info = details_response.json()
                    trailer = get_trailer(tmdb_id)
                    platforms = get_platforms(tmdb_id)
                    
                    if info.get("backdrop_path"):
                        poster = f"https://image.tmdb.org/t/p/w780{info['backdrop_path']}"
                    elif info.get("poster_path"):
                        poster = f"https://image.tmdb.org/t/p/w780{info['poster_path']}"
            except Exception:
                logger.warning("TMDB API request failed")

        # If no results found
        if not info:
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔍 Try Google",
                    url=f"https://www.google.com/search?q={query.replace(' ', '+')}"
                )
            ]])
            msg = await update.message.reply_text(
                "❗ Movie not found. Please check the spelling.",
                reply_markup=buttons
            )
            context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
            return

        # Build response
        caption = build_caption(info, platforms)
        title = info.get("title") or info.get("Title", "")
        dl_link = get_media_link(title)
        buttons = build_buttons(trailer, dl_link)

        # Send response
        if poster:
            try:
                msg = await update.message.reply_photo(
                    photo=crop_16_9(poster),
                    caption=caption,
                    parse_mode=constants.ParseMode.HTML,
                    reply_markup=buttons
                )
            except Exception:
                # Fallback to text if photo fails
                msg = await update.message.reply_text(
                    caption,
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
        logger.info(f"Processed search for: {query}")
        
    except Exception:
        logger.exception("Error in movie search")

# ──────────────────── MAIN ────────────────────
def main():
    try:
        logger.info("Starting Movie Bot...")
        
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not found in environment variables")
            return
            
        app = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))

        # Schedule periodic jobs for each target chat
        for chat_id in TARGET_CHAT_IDS:
            app.job_queue.run_repeating(
                send_latest_media_job, 
                interval=600,  # 10 minutes
                first=10,      # Start after 10 seconds
                chat_id=chat_id
            )
            logger.info(f"Scheduled 10-minute job for chat {chat_id}")

        logger.info("Bot setup complete, starting webhook...")
        
        # Run webhook
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
    
