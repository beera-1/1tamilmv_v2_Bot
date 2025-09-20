import os
import time
import threading
from dotenv import load_dotenv
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# ================== CONFIG ==================
TOKEN = os.getenv('TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
TAMILMV_URL = os.getenv('TAMILMV_URL', 'https://www.1tamilmv.com')
PORT = int(os.getenv('PORT', 8080))
CHANNEL_ID = '-1002585409711'  # replace with your channel ID or username

# Initialize bot
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Flask app
app = Flask(__name__)

# --- In-memory variable to track last fetched movies in this session ---
last_movie_list = []

# --- Load posted movies from file (for persistence) ---
POSTED_FILE = 'posted_movies.json'
try:
    with open(POSTED_FILE, 'r') as f:
        posted_movies = set(json.load(f))
except:
    posted_movies = set()

# --- Save posted movies to file ---
def save_posted_movies():
    with open(POSTED_FILE, 'w') as f:
        json.dump(list(posted_movies), f)

# ------------------ /start command ------------------
@bot.message_handler(commands=['start'])
def random_answer(message):
    text_message = """<b>Hello 👋</b>

<blockquote><b>🎬 Get latest Movies from 1Tamilmv</b></blockquote>

⚙️ <b>How to use me??</b> 🤔

✯ Please enter /view command and you'll get magnet link as well as link to torrent file 😌

<blockquote><b>🔗 Share and Support 💝</b></blockquote>"""

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            '🔗 GitHub 🔗',
            url='https://github.com/SudoR2spr'
        ),
        types.InlineKeyboardButton(
            text="⚡ Powered By",
            url='https://t.me/Opleech_WD'
        )
    )

    bot.send_photo(
        chat_id=message.chat.id,
        photo='https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg',
        caption=text_message,
        reply_markup=keyboard
    )

# ------------------ /view command ------------------
@bot.message_handler(commands=['view'])
def start(message):
    bot.send_message(message.chat.id, "<b>🧲 Please wait for 10 ⏰ seconds</b>")
    global last_movie_list
    # fetch movies
    movie_list, real_dict = tamilmv()

    # filter out already posted movies (since no persistence, this is just last session)
    new_movies = [m for m in movie_list if m not in posted_movies]

    # send magnet links of new movies
    for new_movie in new_movies:
        details_list = real_dict.get(new_movie, [])
        for detail in details_list:
            magnet_link = extract_magnet_link(detail)
            if magnet_link:
                success = False
                while not success:
                    try:
                        bot.send_message(
                            CHANNEL_ID,
                            f"🎬 <b>New Movie Added:</b> {new_movie}\n\n🧲 <b>Magnet Link:</b> <pre>{magnet_link}</pre>",
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                        success = True
                        time.sleep(0.5)
                    except telebot.apihelper.ApiException as e:
                        if '429' in str(e):
                            retry_after = int(str(e).split('retry after')[1].split()[0])
                            print(f"Rate limited. Retry after {retry_after} seconds.")
                            time.sleep(retry_after + 1)
                        else:
                            print(f"Error sending message: {e}")

    # update posted movies set
    for m in new_movies:
        posted_movies.add(m)
    save_posted_movies()

    # update last_movie_list for in-memory tracking
    last_movie_list = list(movie_list)

    # Send a callback message (optional UI)
    combined_caption = """<b><blockquote>🔗 Select a Movie from the list 🎬</blockquote></b>\n\n🔘 Please select a movie:"""
    keyboard = makeKeyboard(movie_list)

    bot.send_photo(
        chat_id=message.chat.id,
        photo='https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg',
        caption=combined_caption,
        reply_markup=keyboard
    )

def extract_magnet_link(detail_text):
    for line in detail_text.splitlines():
        if 'magnet:' in line:
            return line.strip()
    return None

def makeKeyboard(movie_list):
    markup = types.InlineKeyboardMarkup()
    for key, value in enumerate(movie_list):
        markup.add(
            types.InlineKeyboardButton(
                text=value,
                callback_data=f"{key}"
            )
        )
    return markup

def tamilmv():
    mainUrl = TAMILMV_URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    movie_list = []
    real_dict = {}
    try:
        web = requests.get(mainUrl, headers=headers)
        web.raise_for_status()
        soup = BeautifulSoup(web.text, 'lxml')
        temps = soup.find_all('div', {'class': 'ipsType_break ipsContained'})
        if len(temps) < 15:
            logger.warning("Not enough movies found on the page")
            return [], {}
        for i in range(15):
            title = temps[i].find_all('a')[0].text.strip()
            link = temps[i].find('a')['href']
            movie_list.append(title)
            movie_details = get_movie_details(link)
            real_dict[title] = movie_details
        return movie_list, real_dict
    except Exception as e:
        logger.error(f"Error in tamilmv: {e}")
        return [], {}

def get_movie_details(url):
    try:
        html = requests.get(url, timeout=15)
        html.raise_for_status()
        soup = BeautifulSoup(html.text, 'lxml')
        mag = [a['href'] for a in soup.find_all('a', href=True) if 'magnet:' in a['href']]
        filelink = [a['href'] for a in soup.find_all('a', {"data-fileext": "torrent", 'href': True})]
        movie_details = []
        movie_title = soup.find('h1').text.strip() if soup.find('h1') else "Unknown Title"
        for p in range(len(mag)):
            torrent_link = filelink[p] if p < len(filelink) else None
            if torrent_link and not torrent_link.startswith('http'):
                torrent_link = f'{TAMILMV_URL}{torrent_link}'
            magnet_link = mag[p]
            message = f"""
<b>📂 Movie Title:</b>
<blockquote>{movie_title}</blockquote>
🧲 <b>Magnet Link:</b>
<pre>{magnet_link}</pre>"""
            if torrent_link:
                message += f"""
📥 <b>Download Torrent:</b>
<a href="{torrent_link}">🔗 Click Here</a>"""
            else:
                message += """
📥 <b>Torrent File:</b> Not Available"""
            movie_details.append(message)
        return movie_details
    except Exception as e:
        logger.error(f"Error in get_movie_details: {e}")
        return []

# -------- Background auto-updater with in-memory check --------
def auto_update():
    global last_movie_list
    while True:
        try:
            # Fetch latest movies
            current_movie_list, real_dict = tamilmv()

            # Determine new movies not posted in this session
            new_movies = [m for m in current_movie_list if m not in posted_movies]

            # Post new movies
            for new_movie in new_movies:
                details_list = real_dict.get(new_movie, [])
                for detail in details_list:
                    magnet_link = extract_magnet_link(detail)
                    if magnet_link:
                        success = False
                        while not success:
                            try:
                                bot.send_message(
                                    CHANNEL_ID,
                                    f"🎬 <b>New Movie Added:</b> {new_movie}\n\n🧲 <b>Magnet Link:</b> <pre>{magnet_link}</pre>",
                                    parse_mode='HTML',
                                    disable_web_page_preview=True
                                )
                                success = True
                                time.sleep(0.5)
                            except telebot.apihelper.ApiException as e:
                                if '429' in str(e):
                                    retry_after = int(str(e).split('retry after')[1].split()[0])
                                    print(f"Rate limited. Retry after {retry_after} seconds.")
                                    time.sleep(retry_after + 1)
                                else:
                                    print(f"Error in auto_update message send: {e}")

            # Mark newly posted movies as posted
            for m in new_movies:
                posted_movies.add(m)
            save_posted_movies()

            # Update last_movie_list for in-memory comparison
            last_movie_list = list(current_movie_list)

        except Exception as e:
            logger.error(f"Error in auto_update: {e}")

        time.sleep(300)  # Check every 5 mins

# ----------------- Webhook routes -----------------
@app.route('/')
def health_check():
    return "Angel Bot Healthy", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 403

# ----------------- Main execution -----------------
if __name__ == "__main__":
    save_posted_movies()  # save initial state if any
    threading.Thread(target=auto_update, daemon=True).start()

    # Webhook setup
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    # Run Flask app
    app.run(host='0.0.0.0', port=PORT)
