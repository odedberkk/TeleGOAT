# main.py
import os
from flask import Flask, send_from_directory
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pydub import AudioSegment

# ====== Configuration ======
TOKEN = os.getenv("BOT_API_KEY")
PORT = int(os.environ.get("PORT", 5000))
PUBLIC_FOLDER = "public/audio"
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

app = Flask(__name__)

# ====== Telegram Bot Setup ======
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Send me a voice message and I will give you a playable MP3 link!")

def handle_voice(update: Update, context: CallbackContext):
    voice = update.message.voice
    if not voice:
        update.message.reply_text("No voice detected!")
        return

    file = context.bot.get_file(voice.file_id)
    ogg_path = os.path.join(PUBLIC_FOLDER, f"{voice.file_id}.oga")
    mp3_path = os.path.join(PUBLIC_FOLDER, f"{voice.file_id}.mp3")

    # Download the original .oga file
    file.download(ogg_path)

    # Convert to MP3
    AudioSegment.from_file(ogg_path).export(mp3_path, format="mp3")

    # Public URL
    replit_domain = os.environ.get('REPLIT_DEV_DOMAIN') or os.environ.get('REPL_SLUG', 'localhost') + '.' + os.environ.get('REPL_OWNER', '') + '.repl.co'
    public_url = f"https://{replit_domain}/audio/{voice.file_id}.mp3"
    update.message.reply_text(f"Your MP3 is ready: {public_url}")

# Setup updater and dispatcher
updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.voice, handle_voice))

# ====== Flask server to serve MP3s ======
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

# ====== Run both Flask + Telegram ======
if __name__ == "__main__":
    # Start Telegram bot in a separate thread
    import threading
    threading.Thread(target=updater.start_polling, daemon=True).start()
    
    # Start Flask server
    app.run(host="0.0.0.0", port=PORT)
