import os
import time
import threading  # for background auto-update thread
from dotenv import load_dotenv
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
# ============ WOODctaft =================
TOKEN = os.getenv('TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
TAMILMV_URL = os.getenv('TAMILMV_URL', 'https://www.1tamilmv.com')
PORT = int(os.getenv('PORT', 8080))
CHANNEL_ID = '-1002585409711'  # your Telegram channel ID or username

# Initialize bot
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Flask app
app = Flask(__name__)

# Global variables
movie_list = []
real_dict = {}
posted_movies = set()  # to keep track of already posted movies

# --- START command ---
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
            url='https://github.com/SudoR2spr'),
        types.InlineKeyboardButton(
            text="⚡ Powered By",
            url='https://t.me/Opleech_WD'))

    bot.send_photo(
        chat_id=message.chat.id,
        photo='https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg',
        caption=text_message,
        reply_markup=keyboard
    )

# --- /view command ---
@bot.message_handler(commands=['view'])
def start(message):
    bot.send_message(message.chat.id, "<b>🧲 Please wait for 10 ⏰ seconds</b>")
    global movie_list, real_dict
    movie_list, real_dict = tamilmv()

    # Load previous movies
    previous_movies = getattr(start, 'previous_movies', [])

    # Detect new movies
    new_movies = [m for m in movie_list if m not in previous_movies]

    # Send magnet links of new movies
    if new_movies:
        for new_movie in new_movies:
            details_list = real_dict.get(new_movie, [])
            for detail in details_list:
                magnet_link = extract_magnet_link(detail)
                if magnet_link:
                    bot.send_message(
                        CHANNEL_ID,
                        f"🎬 <b>New Movie Added:</b> {new_movie}\n\n🧲 <b>Magnet Link:</b>\n<pre>{magnet_link}</pre>",
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
    # Save current movies for next comparison
    start.previous_movies = list(movie_list)

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
                callback_data=f"{key}")
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
            title = temps[i].findAll('a')[0].text.strip()
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

# --- Background auto-updater ---
def auto_update():
    global posted_movies
    while True:
        try:
            # Fetch latest movies
            movie_list, real_dict = tamilmv()
            # Find new movies not yet posted
            new_movies = [m for m in movie_list if m not in posted_movies]
            # Post magnet links for new movies
            for new_movie in new_movies:
                details_list = real_dict.get(new_movie, [])
                for detail in details_list:
                    magnet_link = extract_magnet_link(detail)
                    if magnet_link:
                        bot.send_message(
                            CHANNEL_ID,
                            f"🎬 <b>New Movie Added:</b> {new_movie}\n\n🧲 <b>Magnet Link:</b>\n<pre>{magnet_link}</pre>",
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
            # Update posted movies set
            posted_movies.update(new_movies)
        except Exception as e:
            logger.error(f"Error in auto_update: {e}")
        time.sleep(300)  # check every 5 minutes

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

if __name__ == "__main__":
    # Start the auto-updater thread
    threading.Thread(target=auto_update, daemon=True).start()

    # Remove webhook and set new one
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    # Run Flask server
    app.run(host='0.0.0.0', port=PORT)
