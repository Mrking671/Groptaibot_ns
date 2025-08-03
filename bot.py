import os
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image

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

# ---------- Config & Secrets ----------
BOT_TOKEN        = os.getenv("BOT_TOKEN")
WEBHOOK_URL      = os.getenv("WEBHOOK_URL")
IMDB_API_KEY     = os.getenv("IMDB_API_KEY")
TMDB_API_KEY     = os.getenv("TMDB_API_KEY")
WELCOME_IMAGE_URL= "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
SERVER1_LINK     = "https://movii-l.vercel.app/"
SERVER2_LINK     = "https://movi-l.netlify.app/"
ADMIN_USERNAME   = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"

# ------------ Helpers -----------
def greeting():
    h = datetime.now().hour
    if 5 <= h < 12: return "Good morning"
    if 12 <= h < 18: return "Good afternoon"
    if 18 <= h < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id):
    resp = requests.get(
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
    ).json().get("results", [])
    for v in resp:
        if v["site"].lower()=="youtube" and v["type"].lower()=="trailer":
            return f"https://www.youtube.com/watch?v={v['key']}"
    return None

def get_platforms(tmdb_id):
    data = requests.get(
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
    ).json().get("results", {}).get(DEFAULT_REGION, {})
    return [p["provider_name"] for p in data.get("flatrate", [])]

def crop_16_9(url):
    try:
        im = Image.open(BytesIO(requests.get(url).content))
        w,h = im.size
        nh = int(w*9/16)
        if h>nh:
            top=(h-nh)//2
            im=im.crop((0,top,w,top+nh))
        buf=BytesIO(); im.save(buf,"PNG"); buf.seek(0)
        return buf
    except:
        return url

async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try:
        await msg.delete()
    except:
        pass

def build_caption(info, platforms):
    t   = info.get("Title") or info.get("title","-")
    yr  = (info.get("Year") or info.get("release_date","-"))[:4]
    rt  = info.get("imdbRating") or info.get("vote_average","-")
    gn  = info.get("Genre") or ", ".join([g["name"] for g in info.get("genres",[])])
    dr  = info.get("Director") or "-"
    pl  = info.get("Plot") or info.get("overview","-")
    ca  = info.get("Actors") or "-"
    cap = (
        f"🎬 <b><u>{t.upper()}</u></b>\n"
        f"┏━━━━━━━━━━━━━━━━━━\n"
        f"┃ <b>Year:</b> {yr}\n"
        f"┃ <b>IMDb:</b> ⭐ {rt}\n"
        f"┃ <b>Genre:</b> {gn}\n"
        f"┃ <b>Director:</b> {dr}\n"
        f"┗━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📝 Plot:</b>\n<em>{pl}</em>\n"
    )
    if ca!="-":
        cap += f"\n<b>🎞️ Cast:</b> {ca}\n"
    if platforms:
        cap += f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"
    return cap

def build_buttons(trailer):
    rows = []
    if trailer:
        rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=trailer)])
    rows.append([
        InlineKeyboardButton("📥 Server 1", url=SERVER1_LINK),
        InlineKeyboardButton("📥 Server 2", url=SERVER2_LINK)
    ])
    return InlineKeyboardMarkup(rows)

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    txt = (
        f"{greeting()}, <b>{name}</b>! 🎬\n\n"
        "I’m your AI Movie Assistant. Send a movie title to get detailed info,"
        "\ntrailer, streaming platforms & download links.\n\n"
        f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trending Movies", callback_data="trending")],
        [InlineKeyboardButton("📥 Server 1", url=SERVER1_LINK)],
        [InlineKeyboardButton("📥 Server 2", url=SERVER2_LINK)],
        [InlineKeyboardButton("👤 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    sent = await update.message.reply_photo(
        WELCOME_IMAGE_URL, caption=txt, parse_mode=constants.ParseMode.HTML, reply_markup=kb
    )
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = requests.get(
        f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
    ).json().get("results", [])[:5]
    txt = "<b>🔥 Trending Movies:</b>\n"
    for i,m in enumerate(data,1):
        txt += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
    sent = await update.callback_query.message.reply_text(txt, parse_mode="HTML")
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text.strip()
    # 1. OMDb (IMDb)
    omdb = requests.get(f"http://www.omdbapi.com/?t={q}&apikey={IMDB_API_KEY}").json()
    if omdb.get("Response")=="True":
        info = omdb; trailer=None; platforms=[]
        poster = omdb.get("Poster") if omdb.get("Poster")!="N/A" else None
    else:
        # 2. TMDb fallback
        sr = requests.get(
            f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={q}"
        ).json().get("results", [])
        if not sr:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔍 Try Google",
                    url=f"https://www.google.com/search?q={q.replace(' ','+')}"
                )
            ]])
            sent = await update.message.reply_text(
                "❗ Movie not found. Check spelling.", reply_markup=kb
            )
            context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})
            return
        tmdb_id = sr[0]["id"]
        details = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
        ).json()
        trailer = get_trailer(tmdb_id)
        platforms = get_platforms(tmdb_id)
        info = details
        poster = (
            f"https://image.tmdb.org/t/p/w780{details.get('backdrop_path')}"
            if details.get("backdrop_path") else None
        )

    cap = build_caption(info, platforms)
    kb  = build_buttons(trailer)
    if poster:
        img = crop_16_9(poster)
        sent = await update.message.reply_photo(
            img, caption=cap, parse_mode="HTML", reply_markup=kb
        )
    else:
        sent = await update.message.reply_text(
            cap, parse_mode="HTML", reply_markup=kb
        )
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})

# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).parse_mode("HTML").build()
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
