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
    client    = MongoClient(MONGO_URI)
    db        = client.get_default_database()
    movies    = db["movie"]
    tvshows   = db["tv"]
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

def get_trailer(tmdb_id: int) -> str | None:
    try:
        if not tmdb_id: return None
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        for v in resp.json().get("results", []):
            if v["site"].lower()=="youtube" and v["type"].lower()=="trailer":
                return f"https://www.youtube.com/watch?v={v['key']}"
    except Exception as e:
        logger.error(f"Error fetching trailer for TMDB ID {tmdb_id}: {e}")
    return None

def get_platforms(tmdb_id: int) -> list[str]:
    try:
        if not tmdb_id: return []
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        data = resp.json().get("results", {}).get(DEFAULT_REGION, {})
        return [p["provider_name"] for p in data.get("flatrate", [])]
    except Exception as e:
        logger.error(f"Error fetching platforms for TMDB ID {tmdb_id}: {e}")
    return []

def crop_16_9(url: str) -> BytesIO | str:
    try:
        if not url: return url
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        w,h = img.size; nh=int(w*9/16)
        if h>nh:
            top=(h-nh)//2
            img=img.crop((0,top,w,top+nh))
        buf=BytesIO(); img.save(buf,"PNG"); buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Image crop failed for URL {url}: {e}")
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        if msg: await msg.delete(); logger.debug("Deleted message")
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")

def build_caption(info: dict, platforms: list[str]) -> str:
    try:
        title  = info.get("Title") or info.get("title","-")
        year   = str(info.get("Year") or info.get("release_date","-"))[:4]
        rating = info.get("imdbRating") or info.get("vote_average","-")
        genre  = "-"
        if info.get("Genre"):
            genre = info["Genre"]
        elif isinstance(info.get("genres"), list):
            g = info["genres"]
            if all(isinstance(x,dict) and "name" in x for x in g):
                genre = ", ".join(x["name"] for x in g)
            elif all(isinstance(x,str) for x in g):
                genre = ", ".join(g)
        director = info.get("Director") or "-"
        plot     = info.get("Plot") or info.get("overview","-")
        cast     = info.get("Actors") or "-"

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
        if cast!="-": cap+=f"\n<b>🎞️ Cast:</b> {cast}\n"
        if platforms: cap+=f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"
        return cap
    except Exception as e:
        logger.error(f"Error building caption: {e}")
        return "Error building movie information"

def get_media_link(title: str) -> str:
    try:
        if not title: return FRONTEND_URL
        doc = movies.find_one({"title": {"$regex": f"^{title}$","$options":"i"}})
        if doc and doc.get("tmdb_id"): return f"{FRONTEND_URL}/mov/{doc['tmdb_id']}"
        doc = tvshows.find_one({"title": {"$regex": f"^{title}$","$options":"i"}})
        if doc and doc.get("tmdb_id"): return f"{FRONTEND_URL}/ser/{doc['tmdb_id']}"
    except Exception as e:
        logger.error(f"Error getting media link: {e}")
    return FRONTEND_URL

def build_buttons(trailer: str | None, dl_link: str) -> InlineKeyboardMarkup:
    try:
        redirect=lambda u: f"https://redirection2.vercel.app/?url={u}"
        rows=[]
        if trailer: rows.append([InlineKeyboardButton("▶️ Watch Trailer",url=redirect(trailer))])
        rows.append([
            InlineKeyboardButton("📥 720p HD",url=redirect(dl_link)),
            InlineKeyboardButton("📥 1080p HD",url=redirect(dl_link)),
        ])
        rows.append([InlineKeyboardButton("📚 Tutorial",url=TUTORIAL_LINK)])
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
        for i,m in enumerate(items,1):
            text+=f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
        msg=await update.callback_query.message.reply_text(text,parse_mode=constants.ParseMode.HTML)
        context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg":msg})
        logger.info("Displayed trending movies")
    except Exception as e:
        logger.error(f"Error in trending_cb: {e}")

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text: return
        query=update.message.text.strip()
        if not query: return
        logger.info(f"Search query: {query}")
        # OMDb
        try:
            omdb_resp=requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",timeout=10)
            omdb_resp.raise_for_status()
            omdb=omdb_resp.json()
        except:
            omdb={"Response":"False"}
        if omdb.get("Response")=="True":
            info=omdb; tmdb_id=None; trailer=None; platforms=[]; poster=omdb.get("Poster") if omdb.get("Poster")!="N/A" else None
        else:
            # TMDb fallback
            try:
                tmdb_s=requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}",timeout=10)
                tmdb_s.raise_for_status()
                results=tmdb_s.json().get("results",[])
            except:
                results=[]
            if not results:
                btn=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Try Google",url=f"https://www.google.com/search?q={query.replace(' ','+')}")]])
                msg=await update.message.reply_text("❗ Movie not found.",parse_mode=constants.ParseMode.HTML,reply_markup=btn)
                context.job_queue.run_once(delete_later,AUTO_DELETE_SECONDS, data={"msg":msg})
                return
            tmdb_id=results[0]["id"]
            try:
                det_r=requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits",timeout=10)
                det_r.raise_for_status()
                details=det_r.json()
            except:
                details=results[0]
            trailer=get_trailer(tmdb_id)
            platforms=get_platforms(tmdb_id)
            info=details
            poster=(f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None)
        caption=build_caption(info,platforms)
        dl_link=get_media_link(info.get("title") or info.get("Title",""))
        buttons=build_buttons(trailer,dl_link)
        if poster:
            img=crop_16_9(poster)
            msg=await update.message.reply_photo(img,caption=caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
        else:
            msg=await update.message.reply_text(caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
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
            await update.message.reply_text("❗ Specify a movie name after /add.")
            return
        query=" ".join(context.args)
        logger.info(f"Broadcasting: {query}")
        # OMDb
        try:
            omdb_r=requests.get(f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}",timeout=10)
            omdb_r.raise_for_status()
            omdb=omdb_r.json()
        except:
            omdb={"Response":"False"}
        if omdb.get("Response")=="True":
            info=omdb; tmdb_id=None; trailer=None; platforms=[]; poster=omdb.get("Poster") if omdb.get("Poster")!="N/A" else None
        else:
            try:
                s_r=requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}",timeout=10)
                s_r.raise_for_status()
                res=s_r.json().get("results",[])
            except:
                res=[]
            if not res:
                await update.message.reply_text("❗ Movie not found.")
                return
            tmdb_id=res[0]["id"]
            try:
                d_r=requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits",timeout=10)
                d_r.raise_for_status()
                details=d_r.json()
            except:
                details=res[0]
            trailer=get_trailer(tmdb_id)
            platforms=get_platforms(tmdb_id)
            info=details
            poster=(f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}" if details.get("backdrop_path") else None)
        caption=build_caption(info,platforms)
        dl_link=get_media_link(info.get("title") or info.get("Title",""))
        buttons=build_buttons(trailer,dl_link)
        if poster:
            img=crop_16_9(poster)
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
        global posted_movie_ids
        logger.info("Running auto-post job")
        count = movies.count_documents({})
        if count==0:
            logger.warning("No movies to auto-post")
            return
        fq={"_id":{"$nin":list(posted_movie_ids)}} if posted_movie_ids else {}
        pipeline=[{"$match":fq},{"$sample":{"size":1}}]
        ml=list(movies.aggregate(pipeline))
        if not ml:
            posted_movie_ids.clear()
            ml=list(movies.aggregate([{"$sample":{"size":1}}]))
        if not ml:
            logger.warning("No movies after reset")
            return
        movie=ml[0]; posted_movie_ids.add(movie["_id"])
        tmdb_id=movie.get("tmdb_id")
        trailer=get_trailer(tmdb_id) if tmdb_id else None
        platforms=get_platforms(tmdb_id) if tmdb_id else []
        caption=build_caption(movie,platforms)
        dl_link=get_media_link(movie.get("title",""))
        buttons=build_buttons(trailer,dl_link)
        poster_url=(f"https://image.tmdb.org/t/p/w780{movie.get('backdrop_path')}" if movie.get("backdrop_path") else None)
        success=0
        for cid in TARGET_CHAT_IDS:
            try:
                if poster_url:
                    img=crop_16_9(poster_url)
                    msg=await context.bot.send_photo(cid,img,caption=caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
                else:
                    msg=await context.bot.send_message(cid,caption,parse_mode=constants.ParseMode.HTML,reply_markup=buttons)
                context.job_queue.run_once(delete_later,AUTO_DELETE_SECONDS,data={"msg":msg})
                success+=1
                logger.info(f"Auto-posted to {cid}")
            except Exception as e:
                logger.error(f"Auto-post to {cid} failed: {e}")
        logger.info(f"Auto-post completed: {success}/{len(TARGET_CHAT_IDS)}")
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
