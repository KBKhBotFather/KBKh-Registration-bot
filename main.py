import os
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import psycopg2
from flask import Flask

# ⚙️ Environment Variables (Render থেকে অটো নিবে)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 UptimeRobot / Render Web Server
app = Flask('')

@app.route('/')
def home():
    return "KBKh Registration Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# 🔌 Database Connection Helper
def get_db_connection():
    return psycopg2.connect(DB_URI)

# 🏢 Teams List
TEAMS = ["Team Alpha", "Team Beta", "Team Gamma", "Team Electron", "Team Proton", "Team Neutron", "Task Control Moderator"]

# 📱 Main Menu Keyboard
def main_menu():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("📝 Register Now"),
        KeyboardButton("🔄 Change FB Name"),
        KeyboardButton("🔑 Already Registered?"),
        KeyboardButton("👤 My Profile"),
        KeyboardButton("🔄 Request Team Change")
    )
    return markup

# ----------------------------------------------------
# 📌 /start Command
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 **KBKh Science Ecosystem-এ আপনাকে স্বাগতম!**\n\n"
        "নিচের বাটনগুলো ব্যবহার করে রেজিস্ট্রেশন, ফেসবুক নাম পরিবর্তন বা অ্যাকাউন্ট রিকভারি করতে পারেন।"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu())

# ----------------------------------------------------
# 👤 1. MY PROFILE
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "👤 My Profile")
def view_profile(message):
    tg_id = message.from_user.id
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, status, security_code FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            fb_name, full_name, unique_id, team, status, code = user
            code_display = f"`{code}`" if code else "*(Approved হওয়ার পর পাবেন)*"
            
            profile_msg = (
                f"👤 **Your KBKh Profile Summary**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {fb_name}\n"
                f"📛 **Full Name:** {full_name}\n"
                f"🆔 **Unique ID:** {unique_id}\n"
                f"🌐 **Team:** {team}\n"
                f"⚡ **Status:** {status}\n"
                f"🔑 **Security Code:** {code_display}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ আপনি এখনো রেজিস্ট্রেশন করেননি। অনুগ্রহ করে `📝 Register Now` বাটনে চাপ দিন।")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ ত্রুটি: {e}")

# ----------------------------------------------------
# 🔄 2. CHANGE FB NAME
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🔄 Change FB Name")
def change_fb_name_start(message):
    msg = bot.send_message(message.chat.id, "✏️ **Enter your current Facebook ID name:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_fb_name_change)

def process_fb_name_change(message):
    new_fb_name = message.text.strip()
    tg_id = message.from_user.id
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()

        if user:
            old_fb_name, team = user
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (new_fb_name, tg_id))
            conn.commit()
            conn.close()

            bot.send_message(message.chat.id, f"✅ আপনার ফেসবুক আইডি নাম সফলভাবে আপডেট করা হয়েছে!\n**নতুন নাম:** {new_fb_name}", parse_mode="Markdown")
            
            if ADMIN_CHAT_ID:
                admin_note = f"🔔 **FB Name Changed!**\n**Old Name:** {old_fb_name}\n**New Name:** {new_fb_name}\n**Team:** {team}"
                bot.send_message(ADMIN_CHAT_ID, admin_note, parse_mode="Markdown")
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ডাটা পাওয়া যায়নি! আপনি নিবন্ধিত নন।")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}")

# ----------------------------------------------------
# 🔑 3. ALREADY REGISTERED?
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🔑 Already Registered?")
def recovery_start(message):
    msg = bot.send_message(message.chat.id, "🔑 **Enter your Security Code:**\n*(যেমন: KBKh20221)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_recovery)

def process_recovery(message):
    sec_code = message.text.strip()
    new_tg_id = message.from_user.id

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name FROM members WHERE security_code = %s", (sec_code,))
        user = cursor.fetchone()

        if user:
            fb_name, full_name, unique_id, team = user
            cursor.execute("UPDATE members SET telegram_id = %s WHERE security_code = %s", (new_tg_id, sec_code))
            conn.commit()
            conn.close()

            success_msg = (
                f"🎉 **Account Restored Successfully!**\n\n"
                f"👤 **FB Name:** {fb_name}\n"
                f"📛 **Full Name:** {full_name}\n"
                f"🆔 **Unique ID:** {unique_id}\n"
                f"🌐 **Team:** {team}\n\n"
                f"আপনার নতুন Telegram ID ডাটাবেজে যুক্ত করা হয়েছে।"
            )
            bot.send_message(message.chat.id, success_msg, parse_mode="Markdown")
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ভুল সিকিউরিটি কোড! সঠিক কোড দিয়ে আবার চেষ্টা করুন।")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}")

# ----------------------------------------------------
# 📝 4. NEW REGISTRATION
# ----------------------------------------------------
user_temp_data = {}

@bot.message_handler(func=lambda msg: msg.text == "📝 Register Now")
def reg_start(message):
    tg_id = message.from_user.id
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM members WHERE telegram_id = %s", (tg_id,))
        existing = cursor.fetchone()
        conn.close()

        if existing:
            bot.send_message(message.chat.id, f"⚠️ আপনি ইতিমধ্যেই নিবন্ধিত! আপনার বর্তমান স্ট্যাটাস: `{existing[0]}`", parse_mode="Markdown")
            return

        user_temp_data[tg_id] = {}
        msg = bot.send_message(message.chat.id, "1️⃣ **Enter your Facebook ID Name:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, reg_get_fullname)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}")

def reg_get_fullname(message):
    tg_id = message.from_user.id
    user_temp_data[tg_id]['fb_name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "2️⃣ **Enter your Full Name (According to ID Card / Official):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, reg_get_unique_id)

def reg_get_unique_id(message):
    tg_id = message.from_user.id
    user_temp_data[tg_id]['full_name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "3️⃣ **Enter your Unique ID (Given by Team):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, reg_select_team)

def reg_select_team(message):
    tg_id = message.from_user.id
    user_temp_data[tg_id]['unique_id'] = message.text.strip()

    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    for team in TEAMS:
        markup.add(KeyboardButton(team))
    
    msg = bot.send_message(message.chat.id, "4️⃣ **Select your Team:**", reply_markup=markup)
    bot.register_next_step_handler(msg, reg_confirm)

def reg_confirm(message):
    tg_id = message.from_user.id
    selected_team = message.text.strip()

    if selected_team not in TEAMS:
        bot.send_message(message.chat.id, "❌ অবৈধ টিম পছন্দ করা হয়েছে। অনুগ্রহ করে আবার রেজিস্ট্রেশন শুরু করুন।", reply_markup=main_menu())
        return

    data = user_temp_data[tg_id]
    data['team_name'] = selected_team
    data['user_type'] = "Task Moderator" if selected_team == "Task Control Moderator" else "General Member"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')",
            (tg_id, data['fb_name'], data['full_name'], data['unique_id'], data['team_name'], data['user_type'])
        )
        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            "✅ **Registration Request Submitted!**\n\nআপনার আবেদনটি এডমিন পেন্ডিংয়ে রাখা হয়েছে। অনুমোদন পেলে আপনাকে সিকিউরিটি কোড পাঠিয়ে দেওয়া হবে।",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        
        if ADMIN_CHAT_ID:
            admin_alert = (
                f"📥 **New Registration Request!**\n\n"
                f"👤 **FB Name:** {data['fb_name']}\n"
                f"📛 **Full Name:** {data['full_name']}\n"
                f"🆔 **Unique ID:** {data['unique_id']}\n"
                f"🌐 **Team:** {data['team_name']}\n"
                f"🆔 **TG ID:** `{tg_id}`"
            )
            bot.send_message(ADMIN_CHAT_ID, admin_alert, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ রেজিস্ট্রেশন ব্যর্থ হয়েছে (সম্ভবত এই Unique ID আগে ব্যবহার করা হয়েছে): {e}", reply_markup=main_menu())

# ----------------------------------------------------
# 🚀 BOT & SERVER LAUNCH
# ----------------------------------------------------
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Registration Bot is Running...")
    bot.infinity_polling()
