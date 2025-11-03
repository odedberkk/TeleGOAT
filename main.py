import os
import threading
import ssl
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pydub import AudioSegment
import paho.mqtt.client as mqtt

# ====== Configuration ======
TOKEN = os.getenv("BOT_API_KEY")
PORT = int(os.environ.get("PORT", 5000))
PUBLIC_FOLDER = "public/audio"
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

# ====== ====== MQTT Configuration ====== ======
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = 8883
MQTT_COMMANDS_TOPIC = os.getenv("MQTT_COMMANDS_TOPIC")
MQTT_RESPONSES_TOPIC = os.getenv("MQTT_RESPONSES_TOPIC")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

# Railway provides the domain via env if set manually
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN", "localhost:5000")

app = Flask(__name__)

# ====== Telegram Bot Handlers ======
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
        
def start(update: Update, context: CallbackContext):
    update.message.reply_text("🎤 Send me a voice message and I'll give you a playable MP3 link!")

def handle_voice(update: Update, context: CallbackContext):
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
    public_url = f"http://{PUBLIC_DOMAIN}/audio/{voice.file_id}.mp3"
    update.message.reply_text(f"✅ Your MP3 is ready:\n{public_url}")
    send_mqtt_message(f"download {public_url}", MQTT_COMMANDS_TOPIC)

# ====== Telegram Setup ======
updater = Updater(TOKEN)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.voice, handle_voice))

# ====== Flask server ======
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

# ====== Run both ======
if __name__ == "__main__":
    threading.Thread(target=updater.start_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
