import os
import threading
import ssl
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pydub import AudioSegment
import paho.mqtt.client as mqtt
import psycopg2

# ====== Configuration ======
TOKEN = os.getenv("BOT_API_KEY")
PORT = int(os.environ.get("PORT", 5000))
PUBLIC_FOLDER = "public/audio"
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

# ====== MQTT Configuration ======
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = 8883
MQTT_COMMANDS_TOPIC = os.getenv("MQTT_COMMANDS_TOPIC")
MQTT_RESPONSES_TOPIC = os.getenv("MQTT_RESPONSES_TOPIC")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

# ====== Auth Configuration ======
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "letmein")  # set in Railway env vars
DATABASE_URL = os.getenv("DATABASE_URL")  # add in Railway (auto-generated for Postgres)

# ====== Domain ======
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN", "localhost:5000")

app = Flask(__name__)


# ====== Database Helpers ======
def get_db_connection():
    if not DATABASE_URL:
        raise Exception("❌ DATABASE_URL is not set in environment variables.")
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    """Create the authorized_users table if not exists"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS authorized_users (
            user_id BIGINT PRIMARY KEY
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def add_authorized_user(user_id):
    """Insert or ignore existing"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO authorized_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING;", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def is_user_authorized(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM authorized_users WHERE user_id = %s;", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

# ====== MQTT Helper ======
def send_mqtt_message(message, topic):
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(topic, message)
        client.disconnect()
        print(f"[MQTT] Sent: {message}")
    except Exception as e:
        print(f"[MQTT] Error: {e}")

# ====== Telegram Handlers ======
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎤 Send me a voice message and I'll give you a playable MP3 link!\n"
        "🔒 Please authorize first by sending /auth <password>"
    )

def auth(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if len(context.args) != 1:
        update.message.reply_text("Usage: /auth <password>")
        return

    if context.args[0] == BOT_PASSWORD:
        add_authorized_user(user_id)
        update.message.reply_text("✅ You are now authorized!")
    else:
        update.message.reply_text("❌ Wrong password!")

def handle_voice(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if not is_user_authorized(user_id):
        update.message.reply_text("🚫 You are not authorized. Please use /auth <password> first.")
        return

    voice = update.message.voice
    if not voice:
        update.message.reply_text("No voice detected!")
        return

    file = context.bot.get_file(voice.file_id)
    
    ogg_path = os.path.join(PUBLIC_FOLDER, f"{voice.file_id}.oga")
    mp3_path = os.path.join(PUBLIC_FOLDER, f"{voice.file_id}.mp3")

    # Download and convert
    file.download(ogg_path)
    AudioSegment.from_file(ogg_path).export(mp3_path, format="mp3")

    # Construct public URL
    public_url = f"https://{PUBLIC_DOMAIN}/audio/{voice.file_id}.mp3"
    update.message.reply_text(f"✅ Your MP3 is ready:\n{public_url}")

    # Send MQTT message
    send_mqtt_message(f"download {public_url}", MQTT_COMMANDS_TOPIC)

# ====== Telegram Setup ======
updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("auth", auth))
dp.add_handler(MessageHandler(Filters.voice, handle_voice))

# ====== Flask server ======
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

# ====== Run both ======
if __name__ == "__main__":
    init_db()
    threading.Thread(target=updater.start_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
