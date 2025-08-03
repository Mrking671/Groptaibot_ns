import os
import requests
import google.generativeai as genai
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from datetime import datetime
from PIL import Image
from io import BytesIO

# --- ENVIRONMENT CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY")  # Get your own OMDB API key
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # Get your TMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- CONSTANTS: replace values below ---
WELCOME_IMAGE_URL = "https://graph.org/file/2de3c18c07ec3f9ce8c1f.jpg"
SERVER1_LINK = "https://movi-l.netlify.app/"
SERVER2_LINK = "https://movii-l.vercel.app/"
ADMIN_USERNAME = "@Lordsakunaa"

# --- UTILITY FUNCTIONS ---
def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Good morning"
    elif 12 <= hour < 18: return "Good afternoon"
    elif 18 <= hour < 22: return "Good evening"
    else: return "Good night"

def modern_movie_ui(data, poster_url, server1, server2):
    # Pretty formatting for movie details
    text = (
        f"🎬 <b>Title:</b> {data.get('Title') or data.get('title')}\n"
        f"📅 <b>Year:</b> {data.get('Year',data.get('release_date','-'))[:4]}\n"
        f"⭐ <b>IMDb Rating:</b> {data.get('imdbRating',data.get('vote_average','N/A'))}\n"
        f"🎭 <b>Genre:</b> {data.get('Genre',data.get('genres','N/A'))}\n"
        f"🎥 <b>Director:</b> {data.get('Director',data.get('director','-'))}\n"
        f"📝 <b>Plot:</b> {data.get('Plot',data.get('overview','-'))}\n"
        f"🎞️ <b>Cast:</b> {data.get('Actors',data.get('cast','-'))}\n"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Server 1", url=server1),
         InlineKeyboardButton("📥 Server 2", url=server2)]
    ])
    return text, poster_url, buttons

def search_tmdb(movie_name):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    res = requests.get(url).json()
    if res.get('results'): return res['results'][0]
    return None

def tmdb_movie_details(tmdb_id):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
    res = requests.get(url).json()
    # Cast and genres as comma-separated strings
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
        # Crop/resize to 16:9
        w, h = img.size
        desired_h = int(w * 9 / 16)
        if h > desired_h:
            # vertical crop
            top = (h - desired_h) // 2
            img = img.crop((0, top, w, top + desired_h))
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
    except Exception:
        return img_url  # fallback: return original URL

def google_search_button(query):
    url = f"https://www.google.com/search?q={query.replace(' ','+')}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search Google", url=url)]])

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    greet = get_greeting()
    fname = user.first_name or "there"
    msg = (
        f"{greet}, <b>{fname}</b>! 👋\n\n"
        "I'm your personal AI Movie Assistant bot. "
        "Discover movies, get recommendations, or download via premium servers.\n"
        "<i>Made with ❤️ by</i> @Lordsakunaa"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Recommend Movie", callback_data="recommend_movie")],
        [InlineKeyboardButton("📥 Download Server 1", url=SERVER1_LINK)],
        [InlineKeyboardButton("📥 Download Server 2", url=SERVER2_LINK)],
        [InlineKeyboardButton("👤 Admin Support", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    await update.message.reply_photo(WELCOME_IMAGE_URL, caption=msg, parse_mode="HTML", reply_markup=buttons)

async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    movie_name = update.message.text
    # 1. Try IMDb (OMDb)
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    res = requests.get(url)
    data = res.json()
    if data.get("Response") == "True":
        poster = data.get("Poster", None)
        poster_obj = get_16_9_img(poster) if (poster and poster != 'N/A') else None
        text, _, buttons = modern_movie_ui(data, poster, SERVER1_LINK, SERVER2_LINK)
        if poster_obj:
            await context.bot.send_photo(chat_id=update.effective_chat.id,
                                         photo=poster_obj,
                                         caption=text,
                                         parse_mode="HTML", reply_markup=buttons)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=buttons)
        return
    # 2. Try TMDb
    tmdb_result = search_tmdb(movie_name)
    if tmdb_result:
        details = tmdb_movie_details(tmdb_result['id'])
        poster_url = details.get("Poster", None)
        poster_obj = get_16_9_img(poster_url) if poster_url else None
        text, _, buttons = modern_movie_ui(details, poster_url, SERVER1_LINK, SERVER2_LINK)
        if poster_obj:
            await context.bot.send_photo(chat_id=update.effective_chat.id,
                                         photo=poster_obj,
                                         caption=text,
                                         parse_mode="HTML", reply_markup=buttons)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=buttons)
        return
    # 3. Not found: spelling?
    reply = (
        "❗ <b>Movie not found.</b>\n"
        "Please check your spelling or try searching on Google:"
    )
    await update.message.reply_text(reply, parse_mode="HTML",
                                    reply_markup=google_search_button(movie_name))

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Please specify a genre:\n/recommend horror\n/recommend action")
        return
    genre_query = context.args[0]
    url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres=&sort_by=vote_average.desc&vote_count.gte=1000"
    genres_res = requests.get(f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB_API_KEY}").json()
    genres_map = {g['name'].lower(): g['id'] for g in genres_res.get('genres',[])}
    if genre_query.lower() in genres_map:
        genre_id = genres_map[genre_query.lower()]
        genre_url = f"{url}&with_genres={genre_id}"
        data = requests.get(genre_url).json()
        results = data.get('results', [])[:5]
        msg = "<b>Top 5 recommended movies:</b>\n"
        for i, m in enumerate(results, 1):
            msg += f"{i}. {m['title']} ({m['release_date'][:4]})\n"
        await update.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text("Invalid genre. Try genres like: horror, action, comedy, drama.")

async def upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://api.themoviedb.org/3/movie/upcoming?api_key={TMDB_API_KEY}&language=en-US"
    res = requests.get(url).json()
    results = res.get('results', [])[:5]
    msg = "<b>Upcoming releases this month:</b>\n"
    for i, m in enumerate(results, 1):
        title = m['title']
        rel = m['release_date']
        msg += f"{i}. {title} (Releasing: {rel})\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "recommend_movie":
        await query.answer()
        await query.message.reply_text("Use /recommend <genre> to get genre-based recommendations!")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("upcoming", upcoming))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.add_handler(MessageHandler(filters.ALL, button_handler))
    # Run webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
