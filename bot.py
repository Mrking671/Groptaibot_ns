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
BOT_TOKEN           = os.getenv("BOT_TOKEN")
WEBHOOK_URL         = os.getenv("WEBHOOK_URL")
IMDB_API_KEY        = os.getenv("IMDB_API_KEY")
TMDB_API_KEY        = os.getenv("TMDB_API_KEY")
MONGO_URI           = os.getenv("MONGO_URI")
FRONTEND_URL        = "https://frontend-flyvio.vercel.app"
TUTORIAL_LINK       = "https://t.me/disneysworl_d"
WELCOME_IMAGE_URL   = "https://ar-hosting.pages.dev/1742397369670.jpg"
ADMIN_USERNAME      = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"

TARGET_CHAT_IDS = [
    -1001878181555,
    -1001675134770,
    -1001955515603,
]

BROADCAST_CHANNEL_ID = -1002097771669

# ──────────────────── DATABASE ────────────────────
try:
    client       = MongoClient(MONGO_URI)
    db           = client.get_default_database()
    movies       = db["movie"]
    tvshows      = db["tv"]
    herosection  = db["herosection"]   # NEW collection for auto-post
    logger.info("Database connection established successfully")
except Exception as e:
    logger.error(f"Failed to connect to database: {e}")
    raise

posted_movie_ids = set()

# ──────────────────── HELPERS ────────────────────
def greeting() -> str:
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int, media_type: str = "movie") -> str | None:
    try:
        if not tmdb_id: return None
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        for v in resp.json().get("results", []):
            if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception as e:
        logger.error(f"Error fetching trailer for TMDB ID {tmdb_id}: {e}")
    return None

def get_platforms(tmdb_id: int, media_type: str = "movie") -> list[str]:
    try:
        if not tmdb_id: return []
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        data = resp.json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception as e:
        logger.error(f"Error fetching platforms for TMDB ID {tmdb_id}: {e}")
    return []

def crop_16_9(url: str) -> BytesIO | str | None:
    try:
        if not url or url in ["N/A", ""]: return None
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        w, h = img.size; nh = int(w * 9 / 16)
        if h > nh:
            top = (h-nh)//2
            img  = img.crop((0,top,w,top+nh))
        buf = BytesIO(); img.save(buf,"PNG"); buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Image crop failed for URL {url}: {e}")
        return None

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        if msg: await msg.delete(); logger.debug("Deleted message")
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")

def build_caption(info: dict, platforms: list[str]) -> str:
    try:
        title    = info.get("Title") or info.get("title","-")
        year     = str(info.get("Year") or info.get("release_date") or info.get("release_year","-"))[:4]
        rating   = info.get("imdbRating") or info.get("vote_average") or info.get("rating","-")
        genre    = "-"
        if info.get("Genre"):
            genre = info["Genre"]
        elif isinstance(info.get("genres"), list):
            g = info["genres"]
            if all(isinstance(x,dict) and "name" in x for x in g):
                genre = ", ".join(x["name"] for x in g)
            elif all(isinstance(x,str) for x in g):
                genre = ", ".join(g)
        elif info.get("genre"):
            genre = info["genre"]
        director = info.get("Director") or info.get("director") or "-"
        plot     = info.get("Plot") or info.get("overview") or info.get("description","-")
        cast     = info.get("Actors") or info.get("cast") or "-"

        cap = (
            f"🎬 <b><u>{title.upper()}</u></b>\n"
            f"┏━━━━━━━━━━━━━━━━━━\n"
            f"┃ <b>Year:</b> {year}\n"
            f"┃ <b>IMDb:</b> ⭐ {rating}\n"
            f"┃ <b>Genre:</b> {genre}\n"
            f"┃ <b>Director:</b> {director}\n"
            f"┗━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📝 Plot:</b>\n<em>{plot}</em>\n"
        )
        if cast != "-": cap += f"\n<b>🎞️ Cast:</b> {cast}\n"
        if platforms: cap += f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"
        return cap
    except Exception as e:
        logger.error(f"Error building caption: {e}")
        return "Error building movie information"

def get_media_link(title: str) -> str:
    try:
        if not title: return FRONTEND_URL
        doc = movies.find_one({"title": {"$regex": f"^{title}$", "$options":"i"}})
        if doc and doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/mov/{doc['tmdb_id']}"
        doc = tvshows.find_one({"title": {"$regex": f"^{title}$", "$options":"i"}})
        if doc and doc.get("tmdb_id"):
            return f"{FRONTEND_URL}/ser/{doc['tmdb_id']}"
    except Exception as e:
        logger.error(f"Error getting media link: {e}")
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str) -> InlineKeyboardMarkup:
    try:
        redirect = lambda u: f"https://redirection2.vercel.app/?url={u}"
        rows = []
        if trailer: rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=redirect(trailer))])
        rows.append([
            InlineKeyboardButton("📥 720p HD", url=redirect(dl_link)),
            InlineKeyboardButton("📥 1080p HD", url=redirect(dl_link)),
        ])
        rows.append([InlineKeyboardButton("📚 Tutorial", url=TUTORIAL_LINK)])
        return InlineKeyboardMarkup(rows)
    except Exception as e:
        logger.error(f"Error building buttons: {e}")
        return InlineKeyboardMarkup([])

# ──────────────────── HANDLERS ────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception during update handling: {context.error}", exc_info=context.error)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message: return
        name = update.effective_user.first_name or "there"
        text = (
            f"{greeting()}, <b>{name}</b>! 🎬\n\n"
            "ᴡᴇʟᴄᴏᴍᴇ 🎉 ᴛᴏ ᴍᴏᴠɪ-ʟ ᴡᴇʙsɪᴛᴇ ᴏғғɪᴄɪᴀʟ ʙᴏᴛ,\n"
            "ᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ᴀɴᴅ sᴇᴇ ᴍᴀɢɪᴄ.\n\n"
            f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ᴛʀᴇɴᴅɪɴɢ",callback_data="trending")],
            [InlineKeyboardButton("👤 ʜᴇʟᴘ",url=f"https://t.me/{ADMIN_USERNAME}")]
        ])
        msg = await update.message.reply_photo(
            WELCOME_IMAGE_URL, caption=text,
            parse_mode=constants.ParseMode.HTML, reply_markup=buttons
        )
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg":msg})
        logger.info(f"Handled /start for {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in start handler: {e}")

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.callback_query: return
        await update.callback_query.answer()
        resp = requests.get(
            f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}",
            timeout=10
        ); resp.raise_for_status()
        items = resp.json().get("results",[])[:5]
        text="<b>🔥 Trending Movies:</b>\n\n"
        for i, m in enumerate(items, 1):
            text += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
        msg = await update.callback_query.message.reply_text(text,parse_mode=constants.ParseMode.HTML)
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg":msg})
        logger.info("Displayed trending movies")
    except Exception as e:
        logger.error(f"Error in trending_cb: {e}")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text: return
        query = update.message.text.strip()
        if not query: return
        logger.info(f"Search query: {query}")

        # First, try finding in local DB: movies, then tvshows
        doc = movies.find_one({"title": {"$regex": f"^{query}$", "$options":"i"}})
        result_type = "movie"
        if not doc:
            doc = tvshows.find_one({"title": {"$regex": f"^{query}$", "$options":"i"}})
            result_type = "tv" if doc else "movie"

        info = None; tmdb_id = None; trailer = None; platforms = []; poster = None

        if doc:  # Found locally
            info = doc
            tmdb_id = doc.get("tmdb_id")
            media_type = "movie" if result_type == "movie" else "tv"
            trailer = get_trailer(tmdb_id, media_type)
            platforms = get_platforms(tmdb_id, media_type)
            poster = doc.get("backdrop") or doc.get("poster")
        else:
            # OMDb search as before
            try:
                omdb_resp = requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",timeout=10)
                omdb_resp.raise_for_status()
                omdb = omdb_resp.json()
            except:
                omdb = {"Response":"False"}
            if omdb.get("Response") == "True":
                info=omdb; tmdb_id = None; trailer = None; platforms = []
                poster = omdb.get("Poster") if omdb.get("Poster")!="N/A" else None
            else:
                # TMDb fallback – Search Show first, then Movie
                tmdb_searches = [
                    ("movie", f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"),
                    ("tv", f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={query}")
                ]
                results = []
                result_type = "movie"
                for rtype, url in tmdb_searches:
                    try:
                        tmdb_s = requests.get(url,timeout=10)
                        tmdb_s.raise_for_status()
                        res = tmdb_s.json().get("results", [])
                        if res:
                            results = res
                            result_type = rtype
                            break
                    except:
                        continue
                if not results:
                    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Try Google",url=f"https://www.google.com/search?q={query.replace(' ','+')}")]])
                    msg = await update.message.reply_text("❗ Movie/Series not found.",parse_mode=constants.ParseMode.HTML,reply_markup=btn)
                    context.job_queue.run_once(delete_later,AUTO_DELETE_SECONDS, data={"msg":msg})
                    return
                tmdb_id = results[0]["id"]
                # Get details
                detail_url = f"https://api.themoviedb.org/3/{result_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
                try:
                    det_r = requests.get(detail_url,timeout=10)
                    det_r.raise_for_status()
                    details = det_r.json()
                except:
                    details = results[0]
                trailer = get_trailer(tmdb_id, result_type)
                platforms = get_platforms(tmdb_id, result_type)
                info = details
                poster = (f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None)
        caption = build_caption(info, platforms)
        # Get proper link
        media_link = get_media_link(info.get("title") or info.get("Title",""))
        if media_link == FRONTEND_URL and tmdb_id:
            media_link = f"{FRONTEND_URL}/{'mov' if result_type=='movie' else 'ser'}/{tmdb_id}"
        buttons = build_buttons(trailer, media_link)
        img = crop_16_9(poster)
        if img:
            msg = await update.message.reply_photo(img,caption=caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
        else:
            msg = await update.message.reply_text(caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
        context.job_queue.run_once(delete_later,AUTO_DELETE_SECONDS,data={"msg":msg})
        logger.info(f"Completed search for {query}")
    except Exception as e:
        logger.error(f"Error in movie_search: {e}")
        try:
            await update.message.reply_text("❗ An error occurred. Please try again.")
        except:
            pass

async def add_movie_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message: return
        if not context.args:
            await update.message.reply_text("❗ Specify a movie/series name after /add.")
            return
        query = " ".join(context.args)
        logger.info(f"Broadcasting: {query}")

        doc = movies.find_one({"title": {"$regex": f"^{query}$", "$options":"i"}})
        result_type = "movie"
        if not doc:
            doc = tvshows.find_one({"title": {"$regex": f"^{query}$", "$options":"i"}})
            result_type = "tv" if doc else "movie"
        info = None; tmdb_id=None; trailer=None; platforms=[]; poster=None

        if doc:
            info = doc
            tmdb_id = doc.get("tmdb_id")
            media_type = "movie" if result_type == "movie" else "tv"
            trailer = get_trailer(tmdb_id, media_type)
            platforms = get_platforms(tmdb_id, media_type)
            poster = doc.get("backdrop") or doc.get("poster")
        else:
            try:
                omdb_r = requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",timeout=10)
                omdb_r.raise_for_status()
                omdb = omdb_r.json()
            except:
                omdb = {"Response":"False"}
            if omdb.get("Response") == "True":
                info = omdb; tmdb_id = None; trailer = None; platforms = []
                poster = omdb.get("Poster") if omdb.get("Poster")!="N/A" else None
            else:
                tmdb_searches = [
                    ("movie", f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"),
                    ("tv", f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={query}")
                ]
                res = []; result_type="movie"
                for rtype, url in tmdb_searches:
                    try:
                        s_r = requests.get(url,timeout=10)
                        s_r.raise_for_status()
                        rx = s_r.json().get("results", [])
                        if rx:
                            res = rx
                            result_type = rtype
                            break
                    except:
                        continue
                if not res:
                    await update.message.reply_text("❗ Movie/Series not found.")
                    return
                tmdb_id = res[0]["id"]
                detail_url = f"https://api.themoviedb.org/3/{result_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
                try:
                    d_r = requests.get(detail_url,timeout=10)
                    d_r.raise_for_status()
                    details = d_r.json()
                except:
                    details = res
                trailer = get_trailer(tmdb_id, result_type)
                platforms = get_platforms(tmdb_id, result_type)
                info = details
                poster = (f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None)
        caption = build_caption(info,platforms)
        media_link = get_media_link(info.get("title") or info.get("Title",""))
        if media_link == FRONTEND_URL and tmdb_id:
            media_link = f"{FRONTEND_URL}/{'mov' if result_type=='movie' else 'ser'}/{tmdb_id}"
        buttons = build_buttons(trailer,media_link)
        img = crop_16_9(poster)
        if img:
            await context.bot.send_photo(BROADCAST_CHANNEL_ID,img,caption=caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
        else:
            await context.bot.send_message(BROADCAST_CHANNEL_ID,caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
        await update.message.reply_text(f"✅ Broadcasted '{query}'")
        logger.info(f"Broadcasted {query}")
    except Exception as e:
        logger.error(f"Error in add_movie_broadcast: {e}")
        try: await update.message.reply_text("❗ Broadcast error. Try again.")
        except: pass

AUTO_POST_INTERVAL = 600

async def auto_post_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        hero_count = herosection.count_documents({})
        if hero_count == 0:
            logger.warning("No hero movies to auto-post")
            return

        pipeline = [{"$sample": {"size": 1}}]
        docs = list(herosection.aggregate(pipeline))
        if not docs: return

        movie = docs[0]
        title = movie.get("title", "-")
        tmdb_id = movie.get("tmdb_id")
        media_type = movie.get("media_type", "movie")
        year = movie.get("release_year", "-")
        rating = movie.get("rating", "-")
        genre = ", ".join(movie.get("genres", []))
        plot = movie.get("description", "-")
        poster_url = movie.get("backdrop") or movie.get("poster") or None

        # Optionally enrich with TMDb APIs (can be skipped if not needed)
        trailer = get_trailer(tmdb_id, media_type) if tmdb_id else None
        platforms = get_platforms(tmdb_id, media_type) if tmdb_id else []
        caption = (
            f"🎬 <b><u>{title.upper()}</u></b>\n"
            f"┏━━━━━━━━━━━━━━━━━━\n"
            f"┃ <b>Year:</b> {year}\n"
            f"┃ <b>IMDb:</b> ⭐ {rating}\n"
            f"┃ <b>Genre:</b> {genre}\n"
            f"┗━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📝 Plot:</b>\n<em>{plot}</em>\n"
        )
        if platforms:
            caption += f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"

        dl_link = f"{FRONTEND_URL}/{'mov' if media_type=='movie' else 'ser'}/{tmdb_id}"
        buttons = build_buttons(trailer, dl_link)
        img = crop_16_9(poster_url)
        for cid in TARGET_CHAT_IDS:
            try:
                if img:
                    await context.bot.send_photo(cid, img, caption=caption, parse_mode=constants.ParseMode.HTML, reply_markup=buttons)
                else:
                    await context.bot.send_message(cid, caption, parse_mode=constants.ParseMode.HTML, reply_markup=buttons)
                context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg":None})
            except Exception as e:
                logger.error(f"Auto-post to {cid} failed: {e}")
        logger.info("Auto-hero-post completed.")
    except Exception as e:
        logger.error(f"Error in auto_post_job: {e}")

def main():
    try:
        logger.info("Starting bot")
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
        app.add_handler(CommandHandler("add", add_movie_broadcast))
        app.add_error_handler(error_handler)
        app.job_queue.run_repeating(auto_post_job, interval=AUTO_POST_INTERVAL, first=10)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT",10000)),
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
