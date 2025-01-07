import os
import random
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
IMDB_API_KEY = os.getenv("IMDB_API_KEY", "f054c7d2")  # Default IMDb API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyB4pvkedwMTVVjPp-OzbmTL8SgVJILBI8M")  # Default Gemini API key

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Function to generate AI content
def generate_ai_content(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text if response else "No response generated."
    except Exception as e:
        print(f"Error generating AI response: {e}")
        return "Error generating AI response."

# Function to delete bot's messages after a delay
async def delete_bot_message(context):
    data = context.job.data
    message = data.get("message")

    if message:
        try:
            await message.delete()
        except Exception as e:
            print(f"Error deleting message: {e}")

# Greeting based on time of day
def get_time_based_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good Morning!"
    elif 12 <= hour < 18:
        return "Good Afternoon!"
    elif 18 <= hour < 22:
        return "Good Evening!"
    else:
        return "Good Night!"

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = get_time_based_greeting()
    welcome_text = f"{greeting}😊\n\nɪ'ᴍ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɪ ʙᴏᴛ ʜᴇʟᴘ ʏᴏᴜ ᴛᴏ ғɪɴᴅ ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴍᴏᴠɪᴇs ᴅᴇᴛᴀɪʟs.\nᴊᴜsᴛ ᴛʏᴘᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ʏᴏᴜ ᴍᴏᴠɪᴇ ᴅᴇᴛᴀɪʟs ᴀs ᴡᴇʟʟ ᴀs ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ.\n\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗.\n𝗠𝗔𝗗𝗘 𝗪𝗜𝗧𝗛 ❤ 𝗯𝘆 @Lordsakunaa"
    message = await update.message.reply_text(welcome_text)

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

# Welcome new members with custom square image
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        user_name = new_member.full_name or "Unknown User"
        user_id = new_member.id
        username = new_member.username or "No Username"

        # Fetch user profile photo
        try:
            photos = await context.bot.get_user_profile_photos(user_id)
            if photos.total_count > 0:
                photo_file = await context.bot.get_file(photos.photos[0][0].file_id)
                photo_bytes = await photo_file.download_as_bytearray()
                user_photo = Image.open(io.BytesIO(photo_bytes))
            else:
                user_photo = Image.new("RGB", (400, 400), (128, 128, 128))  # Default gray
        except Exception as e:
            print(f"Error fetching profile photo: {e}")
            user_photo = Image.new("RGB", (400, 400), (128, 128, 128))  # Default gray

        # Create a square image (400x400) with circular DP
        background = Image.new("RGB", (400, 400), "white")
        draw = ImageDraw.Draw(background)

        # Circular mask for user DP
        user_photo = user_photo.resize((300, 300)).convert("RGBA")
        mask = Image.new("L", user_photo.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0) + user_photo.size, fill=255)
        background.paste(user_photo, (50, 50), mask)

        # Add username at the bottom center of the image
        try:
            font = ImageFont.truetype(random.choice(["arial.ttf", "times.ttf", "calibri.ttf"]), 24)
        except IOError:
            font = ImageFont.load_default()

        # Calculate text size using font.getbbox()
        text_bbox = font.getbbox(user_name)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (400 - text_width) // 2
        draw.text((text_x, 350), user_name, fill="black", font=font, align="center")

        # Save the image to bytes
        output = io.BytesIO()
        background.save(output, format="PNG")
        output.seek(0)

        # Send the generated image to the group
        try:
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=output,
                caption=f"𝐖𝐄𝐋𝐂𝐎𝐌𝐄❤\n\n👤 Name: {user_name}\n🆔 ID: {user_id}\n🔗 Username: @{username}\n\nᴛʏᴘᴇ ᴀɴʏ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ ɪ'ʟʟ ᴘʀᴏᴠɪᴅᴇ ɪᴛ ᴛᴏ ʏᴏᴜ😊\nᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴜsᴇ - /ai 𝚢𝚘𝚞𝚛 𝚚𝚞𝚎𝚜𝚝𝚒𝚘𝚗"
            )

            # Schedule deletion after 30 seconds
            context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        except Exception as e:
            print(f"Error sending welcome image: {e}")

# IMDb information fetcher with "Download Now" button
async def fetch_movie_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return  # Exit if the update does not contain text

    movie_name = update.message.text.strip()
    url = f"http://www.omdbapi.com/?t={movie_name}&apikey={IMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if data.get("Response") == "True":
        reply_text = (
            f"🎬 *Title*: {data.get('Title')}\n"
            f"📅 *Year*: {data.get('Year')}\n"
            f"⭐ *IMDb Rating*: {data.get('imdbRating')}\n"
            f"🎭 *Genre*: {data.get('Genre')}\n"
            f"🕒 *Runtime*: {data.get('Runtime')}\n"
            f"🎥 *Director*: {data.get('Director')}\n"
            f"📝 *Plot*: {data.get('Plot')}\n"
            f"🎞️ *Cast*: {data.get('Actors')}\n"
        )
        poster_url = data.get("Poster")
        download_button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Download Now(PREMIUM Only)💛", url="https://telegra.ph/SORRY-You-are-not-premium-user-01-07")]]
        )

        if poster_url != "N/A":
            message = await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=poster_url,
                caption=reply_text,
                parse_mode="Markdown",
                reply_markup=download_button
            )
        else:
            message = await update.message.reply_text(
                reply_text,
                parse_mode="Markdown",
                reply_markup=download_button
            )
    else:
        ai_response = generate_ai_content(f"Can you describe the movie '{movie_name}'?")
        message = await update.message.reply_text(
            f"Movie not found in IMDb. Here's an AI-generated description👇:\n\n{ai_response}😊"
        )

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

# AI response command
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        message = await update.message.reply_text("Please provide a question. Usage: /ai <your question>😊")
        context.job_queue.run_once(delete_bot_message, 100, data={"message": message})
        return

    question = " ".join(context.args)
    ai_reply = generate_ai_content(question)
    message = await update.message.reply_text(ai_reply)

    # Schedule deletion after 30 seconds
    context.job_queue.run_once(delete_bot_message, 100, data={"message": message})

# Main function
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_response))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fetch_movie_info))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Run webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

# Entry point
if __name__ == "__main__":
    main()
