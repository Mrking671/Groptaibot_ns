#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
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

# ────────────────────🔐  ENV & CONSTANTS ────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN")
WEBHOOK_URL   = os.getenv("WEBHOOK_URL")
IMDB_API_KEY  = os.getenv("IMDB_API_KEY")       # OMDb
TMDB_API_KEY  = os.getenv("TMDB_API_KEY")       # TMDb

WELCOME_IMAGE_URL = "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
SERVER1_LINK      = "https://movii-l.vercel.app/"
SERVER2_LINK      = "https://movi-l.netlify.app/"
ADMIN_USERNAME    = "Lordsakunaa"

AUTO_DELETE_SECONDS = 100
DEFAULT_REGION      = "IN"                      # change to "US", "GB", etc.

# Telegram reaction list
REACTIONS = ["❤️", "😂", "😘", "😍", "😊", "😁"]

# ────────────────────🛠  HELPER FUNCTIONS ───────────────────
def greeting() -> str:
    hour = datetime.now().hour
    if   5 <= hour < 12: return "Good morning"
    elif 12 <= hour < 18: return "Good afternoon"
    elif 18 <= hour < 22: return "Good evening"
    return "Good night"

def get_trailer(tmdb_id: int) -> str | None:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
    for v in requests.get(url).json().get("results", []):
        if v["site"].lower() == "youtube" and v["type"].lower() == "trailer":
            return f"https://www.youtube.com/watch?v={v['key']}"
    return None

def get_platforms(tmdb_id: int) -> list[str]:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={TMDB_API_KEY}"
    prov = requests.get(url).json().get("results", {}).get(DEFAULT_REGION, {})
    return [p["provider_name"] for p in prov.get("flatrate", [])]

def crop_16_9(img_url: str) -> BytesIO | str:
    try:
        im = Image.open(BytesIO(requests.get(img_url).content))
        w, h = im.size
        new_h = int(w * 9 / 16)
        if h > new_h:
            top = (h - new_h) // 2
            im = im.crop((0, top, w, top + new_h))
        bio = BytesIO(); im.save(bio, "PNG"); bio.seek(0)
        return bio
    except Exception:
        return img_url

def delete_later(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data.get("msg")
    try: awaitable = msg.delete()
    except Exception: return
    else: return awaitable

# ────────────────────💬  UI BUILDERS ─────────────────────────
def build_caption(info: dict, platforms: list[str]) -> str:
    t   = info.get("Title")  or info.get("title")  or "-"
    yr  = info.get("Year")   or info.get("release_date", "-")[:4]
    rat = info.get("imdbRating") or info.get("vote_average", "-")
    gen = info.get("Genre")  or ", ".join(g.get("name") for g in info.get("genres", []))
    dri = info.get("Director") or "-"
    plo = info.get("Plot")   or info.get("overview", "-")
    cas = info.get("Actors") or "-"

    cap  = (f"🎬 <b><u>{t.upper()}</u></b>\n"
            f"┏━━━━━━━━━━━━━━━━━━\n"
            f"┃ <b>Year:</b> {yr}\n"
            f"┃ <b>IMDb:</b> ⭐ {rat}\n"
            f"┃ <b>Genre:</b> {gen}\n"
            f"┃ <b>Director:</b> {dri}\n"
            f"┗━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📝 Plot:</b>\n<em>{plo}</em>\n")
    if cas and cas != "-":
        cap += f"\n<b>🎞️ Cast:</b> {cas}\n"
    if platforms:
        cap += f"\n<b>📺 Streaming on:</b> {', '.join(platforms)}"
    return cap

def build_buttons(trailer: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if trailer:
        rows.append([InlineKeyboardButton("▶️ Watch Trailer", url=trailer)])
    rows.append([
        InlineKeyboardButton("📥 Server 1", url=SERVER1_LINK),
        InlineKeyboardButton("📥 Server 2", url=SERVER2_LINK)
    ])
    return InlineKeyboardMarkup(rows)

# ────────────────────🤖  HANDLERS ────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    txt  = (f"{greeting()}, <b>{name}</b>! 🎬\n\n"
            "I’m your AI Movie Assistant. Search any film to get details, trailer,\n"
            "streaming availability and download links.\n\n"
            f"<i>Made with ❤️ by</i> @{ADMIN_USERNAME}")
    kb   = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Trending Movies", callback_data="trending")],
            [InlineKeyboardButton("📥 Server 1", url=SERVER1_LINK)],
            [InlineKeyboardButton("📥 Server 2", url=SERVER2_LINK)],
            [InlineKeyboardButton("👤 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")]
          ])
    sent = await update.message.reply_photo(WELCOME_IMAGE_URL, caption=txt,
                                            parse_mode=constants.ParseMode.HTML,
                                            reply_markup=kb)
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})

async def trending_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
    movies = requests.get(url).json().get("results", [])[:5]
    txt = "<b>🔥 Trending Movies:</b>\n"
    for i, m in enumerate(movies, 1):
        txt += f"<b>{i}.</b> {m['title']} ({m.get('release_date','')[:4]})\n"
    msg = await update.callback_query.message.reply_text(txt, parse_mode="HTML")
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": msg})

async def react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add six emoji reactions to every incoming user text."""
    if not update.message: return
    try:
        await context.bot.set_message_reaction(
            chat_id   = update.message.chat_id,
            message_id= update.message.message_id,
            reaction  = [ReactionTypeEmoji(e) for e in REACTIONS]
        )
    except Exception:  # ignore if reactions not allowed
        pass

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await react(update, context)  # add reactions first
    query = update.message.text.strip()

    # 1) OMDb (IMDb)
    omdb = requests.get(
        f"http://www.omdbapi.com/?t={query}&apikey={IMDB_API_KEY}").json()
    if omdb.get("Response") == "True":
        cap = build_caption(omdb, [])
        trailer = None
        poster  = omdb.get("Poster") if omdb.get("Poster") != "N/A" else None
    else:
        # 2) TMDb fallback
        search = requests.get(
            f"https://api.themoviedb.org/3/search/movie"
            f"?api_key={TMDB_API_KEY}&query={query}"
        ).json().get("results", [])
        if not search:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔍 Try Google",
                    url=f"https://www.google.com/search?q={query.replace(' ','+')}"
                )]
            ])
            m = await update.message.reply_text(
                "❗ Movie not found. Please check the spelling.", reply_markup=kb)
            context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": m})
            return

        mid      = search[0]["id"]
        details  = requests.get(
            f"https://api.themoviedb.org/3/movie/{mid}"
            f"?api_key={TMDB_API_KEY}&append_to_response=credits"
        ).json()
        trailer  = get_trailer(mid)
        platforms= get_platforms(mid)
        cap      = build_caption(details, platforms)
        poster   = (f"https://image.tmdb.org/t/p/w780{details['backdrop_path']}"
                    if details.get("backdrop_path") else None)

    kb = build_buttons(trailer)
    if poster:
        img = crop_16_9(poster)
        sent = await update.message.reply_photo(img, caption=cap,
                                                parse_mode="HTML", reply_markup=kb)
    else:
        sent = await update.message.reply_text(cap, parse_mode="HTML", reply_markup=kb)
    context.job_queue.run_once(delete_later, AUTO_DELETE_SECONDS, data={"msg": sent})

# ────────────────────🚀  MAIN ────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).parse_mode("HTML").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(trending_cb, pattern="^trending$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_search))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))

    # Webhook run
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
                
