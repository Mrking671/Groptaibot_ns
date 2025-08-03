import os
import requests
import google.generativeai as genai
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from datetime import datetime
from PIL import Image
from io import BytesIO

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WELCOME_IMAGE_URL = "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
SERVER1_LINK = "https://movi-l.netlify.app/"
SERVER2_LINK = "https://movii-l.vercel.app/"
ADMIN_USERNAME = "Lordsakunaa"
AUTO_DELETE_SECONDS = 100  # Adjust time window as desired

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Good morning"
    elif 12 <= hour < 18: return "Good afternoon"
    elif 18 <= hour < 22: return "Good evening"
    else: return "Good night"

def stylized_movie_ui(data, poster_url, server1, server2):
    title = data.get('Title') or data.get('title', '-')
    year = data.get('Year') or data.get('release_date', '-')[:4]
    rating = data.get('imdbRating') or data.get('vote_average', '-')
    genre = data.get('Genre') or ", ".join([g['name'] for g in data.get('genres', [])]) or "-"
    director = data.get('Director') or "-"
    runtime = data.get('Runtime') or data.get('runtime', None)
    lang = data.get('Language') or data.get('original_language', None)
    country = data.get('Country') or data.get('production_countries', None)
    cast = data.get('Actors') or ", ".join([c['name'] for c in data.get('credits',{}).get('cast',[])[:8]]) or "-"
    boxoffice = data.get('BoxOffice', None)
    awards = data.get('Awards', None)
    plot = data.get('Plot') or data.get('overview', '-')
    top = (
        f"🎬 <b><u>{title.upper()}</u></b>\n"
        f"┏━━━━━━━━━━━\n"
        f"┃ <b>Year:</b> <code>{year}</code>\n"
        f"┃ <b>IMDb:</b> ⭐ <code>{rating}</code>\n"
        f"┃ <b>Genre:</b> {genre}\n"
        f"┃ <b>Director:</b> {director}\n"
        f"┗━━━━━━━━━━━"
    )
    more = ""
    if runtime: more += f"\n⏱ <b>Runtime:</b> {runtime}"
    if lang: more += f"\n🌐 <b>Language:</b> {lang}"
    if country and isinstance(country, str):
        more += f"\n🏳 <b>Country:</b> {country}"
    elif country and isinstance(country, list):
        more += f"\n🏳 <b>Country:</b> {', '.join([c['name'] for c in country])}"
    if boxoffice: more += f"\n💰 <b>Box Office:</b> {boxoffice}"
    if awards: more += f"\n🏆 <b>Awards:</b> {awards}"
    mid = f"\n\n<b>📝 Plot:</b>\n<em>{plot}</em>\n"
    castblock = f"\n<b>🎞️ Cast:</b> {cast}" if cast and cast != "-" else ""
    ui = f"{top}{more}{mid}{castblock}"
    # Add Chrome direct link as a separate button
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download: Server 1", url=server1)],
        [InlineKeyboardButton("📥 Download: Server 1 (Chrome)", url=f"googlechrome://navigate?url={server1}")],
        [InlineKeyboardButton("📥 Download: Server 2", url=server2)],
        [InlineKeyboardButton("📥 Download: Server 2 (Chrome)", url=f"googlechrome://navigate?url={server2}")]
    ])
    return ui, poster_url, buttons

def search_tmdb(movie_name):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    res = requests.get(url).json()
    if res.get('results'): return res['results']
    return None

def tmdb_movie_details(tmdb_id):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
    res = requests.get(url).json()
    genres = ", ".join([g['name'] for g in res.get('genres',[])])
    cast = ", ".join([c['name'] for c in res.get('credits',{}).get('cast',[])[:8]])
    return {
        "Title": res.get('title'),
        "Year": res.get('release_date','')[:4],
        "imdbRating": res.get('vote_average','N/A'),
        "Genre": genres,
        "Director": ", ".join([c['name'] for c in res.get('credits',{}).get('crew',[]) if c.get('job')=="Director"]),
        "Plot": res.get('overview',''),
        "Actors": cast,
        "Poster": f"https://image.tmdb.org/t/p/w780{res.get('backdrop_path')}" if res.get('backdrop_path') else None
    }

def get_16_9_img(img_url):
    try:
        resp = requests.get(img_url)
        img = Image.open(BytesIO(resp.content))
        w, h = img.size
        desired_h = int(w * 9 / 16)
        if h > desired_h:
            top = (h - desired_h) // 2
            img = img.crop((0, top, w, top + desired_h))
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
    except Exception:
        return img_url

def google_search_button(query):
    url = f"https://www.google.com/search?q={query.replace(' ','+')}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search Google", url=url)]])

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    message = job_data.get("message")
    try:
        await message.delete()
    except Exception:
        pass  # Ignore if already deleted

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    greet = get_greeting()
    fname = user.first_name or "there"
    msg = (
        f"{greet}, <b>{fname}</b>! 👋\n\n"
        "I'm your personal AI Movie Assistant bot. "
        "Discover movies, get recommendations, or download via premium servers.\n"
        "<i>Made with ❤️ by</i> @Lordsakunaa"
        "\n\n<i>If you want to open links in Chrome, tap '…' and choose 'Open in browser' or long-press the button link.</i>"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Recommend Movie", callback_data="recommend_movie")],
        [InlineKeyboardButton("📥 Download Server 1", url=SERVER1_LINK)],
        [InlineKeyboardButton("📥 Download Server 2", url=SERVER2_LINK)],
        [InlineKeyboardButton("👤 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    sent = await update.message.reply_photo(WELCOME_IMAGE_URL, caption=msg, parse_mode="HTML", reply_markup=buttons)
    context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    movie_name = update.message.text
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    res = requests.get(url)
    data = res.json()
    if data.get("Response") == "True":
        poster = data.get("Poster", None)
        poster_obj = get_16_9_img(poster) if (poster and poster != 'N/A') else None
        ui, _, buttons = stylized_movie_ui(data, poster, SERVER1_LINK, SERVER2_LINK)
        if poster_obj:
            sent = await context.bot.send_photo(chat_id=update.effective_chat.id,
                                         photo=poster_obj,
                                         caption=ui,
                                         parse_mode="HTML", reply_markup=buttons)
        else:
            sent = await update.message.reply_text(ui, parse_mode="HTML", reply_markup=buttons)
        context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})
        return
    tmdb_result = search_tmdb(movie_name)
    if tmdb_result:
        details = tmdb_movie_details(tmdb_result[0]['id'])
        poster_url = details.get("Poster", None)
        poster_obj = get_16_9_img(poster_url) if poster_url else None
        ui, _, buttons = stylized_movie_ui(details, poster_url, SERVER1_LINK, SERVER2_LINK)
        if poster_obj:
            sent = await context.bot.send_photo(chat_id=update.effective_chat.id,
                                         photo=poster_obj,
                                         caption=ui,
                                         parse_mode="HTML", reply_markup=buttons)
        else:
            sent = await update.message.reply_text(ui, parse_mode="HTML", reply_markup=buttons)
        context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})
        return
    reply = (
        "❗ <b>Movie not found.</b>\n"
        "Please check your spelling or try searching on Google:"
    )
    sent = await update.message.reply_text(reply, parse_mode="HTML",
                                    reply_markup=google_search_button(movie_name))
    context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        sent = await update.message.reply_text("Please specify a genre:\n/recommend horror\n/recommend action")
        context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})
        return
    genre_query = " ".join(context.args).lower()
    genres_res = requests.get(f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB_API_KEY}").json()
    genres_map = {g['name'].lower(): g['id'] for g in genres_res.get('genres',[])}
    if genre_query in genres_map:
        genre_id = genres_map[genre_query]
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=vote_average.desc&vote_count.gte=1000"
        data = requests.get(url).json()
        results = data.get('results', [])[:5]
        msg = "<b>🔥 Top 5 recommended movies:</b>\n"
        for i, m in enumerate(results, 1):
            msg += f"<b>{i}.</b> <u>{m['title']}</u> ({m['release_date'][:4]})\n"
        sent = await update.message.reply_text(msg, parse_mode="HTML")
    else:
        sent = await update.message.reply_text("Invalid genre. Try genres like: horror, action, comedy, drama.")
    context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})

async def upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://api.themoviedb.org/3/movie/upcoming?api_key={TMDB_API_KEY}&language=en-US"
    res = requests.get(url).json()
    results = res.get('results', [])[:5]
    msg = "<b>🎟️ Upcoming releases this month:</b>\n"
    for i, m in enumerate(results, 1):
        title = m['title']
        rel = m['release_date']
        msg += f"<b>{i}.</b> <u>{title}</u> (Releases: <code>{rel}</code>)\n"
    sent = await update.message.reply_text(msg, parse_mode="HTML")
    context.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query and query.data == "recommend_movie":
        await query.answer()
        sent = await query.message.reply_text("Use /recommend <genre> to get genre-based recommendations!")
        query._bot._application.job_queue.run_once(delete_message, AUTO_DELETE_SECONDS, data={"message": sent})

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("upcoming", upcoming))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.add_handler(MessageHandler(filters.ALL, button_handler))
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
