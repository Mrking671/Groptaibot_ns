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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Logging & Error Handling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ðŸ” CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ DATABASE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    movies = db["movie"]
    tvshows = db["tv"]
    logger.info("Database connection established successfully")
except Exception as e:
    logger.error(f"Failed to connect to database: {e}")
    raise

# To track posted movie IDs and avoid repetition
posted_movie_ids = set()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def greeting() -> str:
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int) -> str | None:
    try:
        if not tmdb_id:
            return None
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        for v in response.json().get("results", []):
            if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception as e:
        logger.error(f"Error fetching trailer for TMDB ID {tmdb_id}: {e}")
    return None

def get_platforms(tmdb_id: int) -> list[str]:
    try:
        if not tmdb_id:
            return []
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception as e:
        logger.error(f"Error fetching platforms for TMDB ID {tmdb_id}: {e}")
    return []

def crop_16_9(url: str) -> BytesIO | str:
    try:
        if not url:
            return url
        response = requests.get(url, timeout=10)
        response.raise_for_status()
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
    except Exception as e:
        logger.error(f"Image crop failed for URL {url}: {e}")
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        if msg:
            await msg.delete()
            logger.debug("Message deleted successfully")
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")

def build_caption(info: dict, platforms: list[str]) -> str:
    try:
        title    = info.get("Title") or info.get("title", "-")
        year     = str(info.get("Year") or info.get("release_date", "-"))[:4]
        rating   = info.get("imdbRating") or info.get("vote_average", "-")
        
        # Robust genre handling:
        genre = "-"
        if info.get("Genre"):
            genre = info.get("Genre")
        elif isinstance(info.get("genres", None), list):
            genres = info["genres"]
            if genres:
                if all(isinstance(g, dict) and "name" in g for g in genres):
                    genre = ", ".join(g["name"] for g in genres)
                elif all(isinstance(g, str) for g in genres):
                    genre = ", ".join(genres)
        
        director = info.get("Director") or "-"
        plot     = info.get("Plot") or info.get("overview", "-")
        cast     = info.get("Actors") or "-"

        caption = (
            f"ðŸŽ¬ <b><u>{title.upper()}</u></b>\n"
            f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
            f"â”ƒ <b>Year:</b> {year}\n"
            f"â”ƒ <b>IMDb:</b> â­ {rating}\n"
            f"â”ƒ <b>Genre:</b> {genre}\n"
            f"â”ƒ <b>Director:</b> {director}\n"
            f"â”—â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n\n"
            f"<b>ðŸ“ Plot:</b>\n<em>{plot}</em>\n"
        )
        if cast != "-":
            caption += f"\n<b>ðŸŽžï¸ Cast:</b> {cast}\n"
        if platforms:
            caption += f"\n<b>ðŸ“º Streaming on:</b> {', '.join(platforms)}"
        return caption
    except Exception as e:
        logger.error(f"Error building caption: {e}")
        return "Error building movie information"

def get_media_link(title: str) -> str:
    try:
        if not title:
            return FRONTEND_URL
        doc = movies.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if doc and doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/mov/{doc['tmdb_id']}"
        doc = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
        if doc and doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/ser/{doc['tmdb_id']}"
    except Exception as e:
        logger.error(f"Error getting media link for {title}: {e}")
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str) -> InlineKeyboardMarkup:
    try:
        redirect = lambda url: f"https://redirection2.vercel.app/?url={url}"
        rows: list[list[InlineKeyboardButton]] = []
        if trailer:
            rows.append([InlineKeyboardButton("â–¶ï¸ Watch Trailer", url=redirect(trailer))])
        rows.append([
            InlineKeyboardButton("ðŸ“¥ 720p HD", url=redirect(dl_link)),
            InlineKeyboardButton("ðŸ“¥ 1080p HD", url=redirect(dl_link)),
        ])
        # Tutorial button WITHOUT redirection
        rows.append([InlineKeyboardButton("ðŸ“š Tutorial", url=TUTORIAL_LINK)])
        return InlineKeyboardMarkup(rows)
    except Exception as e:
        logger.error(f"Error building buttons: {e}")
        return InlineKeyboardMarkup([])

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ HANDLERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Exception during handling update: {context.error}", exc_info=context.error)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            logger.warning("Start command received without message")
            return
            
        name = update.effective_user.first_name or "there"
        text = (
            f"{greeting()}, <b>{name}</b>! ðŸŽ¬\n\n"
            "á´¡á´‡ÊŸá´„á´á´á´‡ ðŸŽ‰ á´›á´ á´á´á´ Éª-ÊŸ á´¡á´‡Ê™sÉªá´›á´‡ á´Ò“Ò“Éªá´„Éªá´€ÊŸ Ê™á´á´›,\n"
            "á´›Êá´˜á´‡ á´€É´Ê á´á´á´ Éªá´‡ É´á´€á´á´‡ á´€É´á´… sá´‡á´‡ á´á´€É¢Éªá´„.\n\n"
            f"<i>Made with â¤ï¸ by</i> @{ADMIN_USERNAME}"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ðŸŽ¬ á´›Ê€á´‡É´á´…ÉªÉ´É¢", callback_data="trending")],
            [InlineKeyboardButton("ðŸ‘¤ Êœá´‡ÊŸá´˜", url=f"https://t.me/{ADMIN_USERNAME}")]
        ])
        msg = await update.message.reply_photo(
            WELCOME_IMAGE_URL,
            caption=text,
            parse_mode=constants.ParseMode.HTML,
            reply_markup=buttons
        )
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        logger.info(f"Start command handled for user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in start handler: {e}")

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.callback_query:
            logger.warning("Trending callback received without callback_query")
            return
            
        await update.callback_query.answer()
        response = requests.get(
            f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}",
            timeout=10
        )
        response.raise_for_status()
        results = response.json().get("results", [])[:5]
        
        text = "<b>ðŸ”¥ Trending Movies:</b>\n\n"
        for i, m in enumerate(results, start=1):
            text += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
        msg = await update.callback_query.message.reply_text(text, parse_mode=constants.ParseMode.HTML)
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
        logger.info("Trending movies displayed successfully")
    except Exception as e:
        logger.error(f"Error in trending callback: {e}")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Safe guard against None message or text
        if not update or not update.message or not update.message.text:
            logger.warning(f"Received invalid update in movie_search: {update}")
            return
            
        query = update.message.text.strip()
        if not query:
            logger.warning("Empty query received")
            return
            
        logger.info(f"Movie search query: {query}")

        # Try IMDb via OMDb first
        try:
            omdb_response = requests.get(
                f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",
                timeout=10
            )
            omdb_response.raise_for_status()
            omdb = omdb_response.json()
        except Exception as e:
            logger.error(f"OMDb API error: {e}")
            omdb = {"Response": "False"}

        if omdb.get("Response") == "True":
            info      = omdb
            tmdb_id   = None
            trailer   = None
            platforms = []
            poster    = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
            logger.info(f"Found movie via OMDb: {info.get('Title')}")
        else:
            # Fallback to TMDb
            try:
                tmdb_response = requests.get(
                    f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}",
                    timeout=10
                )
                tmdb_response.raise_for_status()
                search = tmdb_response.json().get("results", [])
            except Exception as e:
                logger.error(f"TMDb search API error: {e}")
                search = []
                
            if not search:
                buttons = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "ðŸ” Try Google",
                        url=f"https://www.google.com/search?q={query.replace(' ', '+')}"
                    )
                ]])
                msg = await update.message.reply_text(
                    "â— Movie not found. Please check the spelling.",
                    parse_mode=constants.ParseMode.HTML,
                    reply_markup=buttons
                )
                context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})
                logger.info(f"Movie not found: {query}")
                return

            tmdb_id = search[0]["id"]
            try:
                details_response = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits",
                    timeout=10
                )
                details_response.raise_for_status()
                details = details_response.json()
            except Exception as e:
                logger.error(f"TMDb details API error: {e}")
                details = search[0]  # Fallback to search result
                
            trailer   = get_trailer(tmdb_id)
            platforms = get_platforms(tmdb_id)
            info      = details
            poster    = (
                f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}"
                if details.get("backdrop_path") else None
            )
            logger.info(f"Found movie via TMDb: {info.get('title')}")

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
        logger.info(f"Movie search completed successfully for: {query}")
    except Exception as e:
        logger.error(f"Error in movie_search handler: {e}")
        try:
            if update and update.message:
                await update.message.reply_text("â— An error occurred while searching. Please try again.")
        except:
            pass

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ ADD MOVIE TO BROADCAST CHANNEL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def add_movie_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            logger.warning("Add command received without message")
            return
            
        if not context.args:
            await update.message.reply_text("â— Please specify a movie name after /add.")
            return

        query = " ".join(context.args)
        logger.info(f"Broadcasting movie: {query}")

        # Try IMDb via OMDb first
        try:
            omdb_response = requests.get(
                f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",
                timeout=10
            )
            omdb_response.raise_for_status()
            omdb = omdb_response.json()
        except Exception as e:
            logger.error(f"OMDb API error in broadcast: {e}")
            omdb = {"Response": "False"}

        if omdb.get("Response") == "True":
            info      = omdb
            tmdb_id   = None
            trailer   = None
            platforms = []
            poster    = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
        else:
            # Fallback to TMDb
            try:
                tmdb_response = requests.get(
                    f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}",
                    timeout=10
                )
                tmdb_response.raise_for_status()
                search = tmdb_response.json().get("results", [])
            except Exception as e:
                logger.error(f"TMDb search API error in broadcast: {e}")
                search = []
                
            if not search:
                await update.message.reply_text("â— Movie not found. Please check the spelling.")
                return

            tmdb_id = search[0]["id"]
            try:
                details_response = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits",
                    timeout=10
                )
                details_response.raise_for_status()
                details = details_response.json()
            except Exception as e:
                logger.error(f"TMDb details API error in broadcast: {e}")
                details = search[0]
                
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

        await update.message.reply_text(f"âœ… Movie '{query}' broadcasted to the channel.")
        logger.info(f"Successfully broadcasted movie: {query}")
    except Exception as e:
        logger.error(f"Error in add_movie_broadcast handler: {e}")
        try:
            if update and update.message:
                await update.message.reply_text("â— An error occurred while broadcasting. Please try again.")
        except:
            pass

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ AUTO-POST JOB â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
AUTO_POST_INTERVAL = 600  # 10 minutes in seconds

async def auto_post_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        global posted_movie_ids
        logger.info("Starting auto-post job")

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
            logger.info("All movies posted, resetting posted_movie_ids")
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

        successful_posts = 0
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
                successful_posts += 1
                logger.info(f"Auto-posted movie to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed auto-post in chat {chat_id}: {e}")

        logger.info(f"Auto-post job completed. Posted to {successful_posts}/{len(TARGET_CHAT_IDS)} chats. Movie: {movie.get('title', 'Unknown')}")
    except Exception as e:
        logger.error(f"Error in auto_post_job: {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ MAIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def main():
    try:
        logger.info("Starting bot application")
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
        app.add_handler(CommandHandler("add", add_movie_broadcast))

        # Add error handler
        app.add_error_handler(error_handler)

        # Schedule auto-post every 10 minutes, starting after 10 seconds
        app.job_queue.run_repeating(auto_post_job, interval=AUTO_POST_INTERVAL, first=10)
        logger.info(f"Auto-post job scheduled every {AUTO_POST_INTERVAL} seconds")

        # Run webhook
        logger.info("Starting webhook server")
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 10000)),
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise

if __name__ == "__main__":
    main()
