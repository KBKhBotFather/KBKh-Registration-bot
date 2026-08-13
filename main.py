import os
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ⚙️ Environment Variables (Render থেকে অটো নিবে)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Server for Render / Uptime
app = Flask('')

@app.route('/')
def home():
    return "KBKh Registration Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# 🔌 Database Connection Helper
def get_db_connection():
    return psycopg2.connect(DB_URI)

# 🏢 Teams & Categories Mapping
TEAMS = ["Team Alpha", "Team Beta", "Team Gamma", "Team Electron", "Team Proton", "Team Neutron"]

TEAM_SLUGS = {
    "alpha": "Team Alpha",
    "beta": "Team Beta",
    "gamma": "Team Gamma",
    "electron": "Team Electron",
    "proton": "Team Proton",
    "neutron": "Team Neutron"
}

user_temp_data = {}

# 🔑 Security Code Generator
def generate_security_code(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nextval('security_code_seq')")
        seq_val = cursor.fetchone()[0]
        return f"KBKh{seq_val}"
    except Exception:
        conn.rollback()
        cursor.execute("SELECT COUNT(*) FROM members WHERE security_code IS NOT NULL")
        cnt = cursor.fetchone()[0] + 101
        return f"KBKh{cnt}"

# 📱 Keyboards
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("📝 Register Now"),
        KeyboardButton("🔄 Change FB Name"),
        KeyboardButton("🔑 Already Registered?"),
        KeyboardButton("👤 My Profile"),
        KeyboardButton("🔄 Request Team Change")
    )
    if str(user_id) == str(ADMIN_CHAT_ID):
        markup.add(
            KeyboardButton("⏳ Pending Registration"),
            KeyboardButton("📋 Members List")
        )
    return markup

def cancel_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

def teams_keyboard():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add(
        KeyboardButton("Team Alpha"),
        KeyboardButton("Team Beta"),
        KeyboardButton("Team Gamma"),
        KeyboardButton("Team Electron"),
        KeyboardButton("Team Proton"),
        KeyboardButton("Team Neutron"),
        KeyboardButton("❌ Cancel")
    )
    return markup

# 🛑 Check Cancel or Menu Switching (Prevents Glitches/Locks)
def check_cancel_or_menu(message):
    text = message.text.strip() if message.text else ""
    if text in ["❌ Cancel", "/cancel"]:
        bot.send_message(message.chat.id, "❌ প্রসেসটি বাতিল করা হয়েছে।", reply_markup=main_menu(message.from_user.id))
        return True, "cancel"
    elif text in ["📝 Register Now", "🔄 Change FB Name", "🔑 Already Registered?", "👤 My Profile", "🔄 Request Team Change", "⏳ Pending Registration", "📋 Members List"]:
        return True, text
    return False, None

def handle_menu_action(message, action):
    if action == "📝 Register Now":
        reg_start(message)
    elif action == "🔄 Change FB Name":
        change_fb_name_start(message)
    elif action == "🔑 Already Registered?":
        recovery_start(message)
    elif action == "👤 My Profile":
        view_profile(message)
    elif action == "🔄 Request Team Change":
        team_change_start(message)
    elif action == "⏳ Pending Registration":
        admin_pending_list_msg(message)
    elif action == "📋 Members List":
        admin_members_list_msg(message)

# ----------------------------------------------------
# 📌 /start Command
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 **KBKh Science Ecosystem-এ আপনাকে স্বাগতম!**\n\n"
        "নিচের বাটনগুলো ব্যবহার করে রেজিস্ট্রেশন বা অন্যান্য সেবা নিতে পারেন।"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))

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
            bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown", reply_markup=main_menu(tg_id))
        else:
            bot.send_message(message.chat.id, "❌ আপনি এখনো রেজিস্ট্রেশন করেননি। অনুগ্রহ করে `📝 Register Now` বাটনে চাপ দিন।", parse_mode="Markdown", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# ----------------------------------------------------
# 🔄 2. CHANGE FB NAME
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🔄 Change FB Name")
def change_fb_name_start(message):
    msg = bot.send_message(
        message.chat.id, 
        "✏️ **Enter your new Facebook Profile Name:**", 
        parse_mode="Markdown", 
        reply_markup=cancel_keyboard()
    )
    bot.register_next_step_handler(msg, process_fb_name_change)

def process_fb_name_change(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

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

            bot.send_message(
                message.chat.id, 
                f"✅ আপনার ফেসবুক আইডি নাম সফলভাবে আপডেট করা হয়েছে!\n**নতুন নাম:** {new_fb_name}", 
                parse_mode="Markdown",
                reply_markup=main_menu(tg_id)
            )

            if ADMIN_CHAT_ID:
                admin_note = f"🔔 **FB Name Changed!**\n**Old Name:** {old_fb_name}\n**New Name:** {new_fb_name}\n**Team:** {team}"
                bot.send_message(ADMIN_CHAT_ID, admin_note, parse_mode="Markdown")
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ডাটা পাওয়া যায়নি! আপনি নিবন্ধিত নন।", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# ----------------------------------------------------
# 🔑 3. ALREADY REGISTERED?
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🔑 Already Registered?")
def recovery_start(message):
    msg = bot.send_message(
        message.chat.id, 
        "🔑 **Enter your Security Code:**", 
        parse_mode="Markdown", 
        reply_markup=cancel_keyboard()
    )
    bot.register_next_step_handler(msg, process_recovery)

def process_recovery(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

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
            bot.send_message(message.chat.id, success_msg, parse_mode="Markdown", reply_markup=main_menu(new_tg_id))
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ভুল সিকিউরিটি কোড! সঠিক কোড দিয়ে আবার চেষ্টা করুন।", reply_markup=main_menu(new_tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(new_tg_id))

# ----------------------------------------------------
# 🔄 4. REQUEST TEAM CHANGE
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🔄 Request Team Change")
def team_change_start(message):
    tg_id = message.from_user.id
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT team_name, status FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if not user or user[1] != 'Approved':
            bot.send_message(message.chat.id, "❌ আপনি এপ্রুভড মেম্বার নন! টিম পরিবর্তন করতে পারবেন না।", reply_markup=main_menu(tg_id))
            return

        user_temp_data[tg_id] = {'old_team': user[0]}
        msg = bot.send_message(
            message.chat.id,
            f"🌐 আপনার বর্তমান টিম: **{user[0]}**\n\nনতুন কোন টিমে যুক্ত হতে চান তা সিলেক্ট করুন:",
            parse_mode="Markdown",
            reply_markup=teams_keyboard()
        )
        bot.register_next_step_handler(msg, process_team_change_request)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

def process_team_change_request(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

    requested_team = message.text.strip()
    tg_id = message.from_user.id

    if requested_team not in TEAMS:
        bot.send_message(message.chat.id, "❌ অবৈধ টিম পছন্দ করা হয়েছে।", reply_markup=main_menu(tg_id))
        return

    old_team = user_temp_data.get(tg_id, {}).get('old_team', 'Unknown')
    if requested_team == old_team:
        bot.send_message(message.chat.id, f"⚠️ আপনি ইতিমধ্যেই **{old_team}**-এ আছেন!", parse_mode="Markdown", reply_markup=main_menu(tg_id))
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO team_change_requests (telegram_id, old_team, requested_team) VALUES (%s, %s, %s)",
            (tg_id, old_team, requested_team)
        )
        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"✅ **টিম পরিবর্তনের আবেদন জমা হয়েছে!**\n**{old_team}** ➔ **{requested_team}**\nএডমিন এটি এপ্রুভ করলে আপনার টিম আপডেট হয়ে যাবে।",
            parse_mode="Markdown",
            reply_markup=main_menu(tg_id)
        )

        if ADMIN_CHAT_ID:
            admin_note = f"🔄 **Team Change Request!**\n🆔 **TG ID:** `{tg_id}`\n**Old Team:** {old_team}\n**New Team:** {requested_team}"
            bot.send_message(ADMIN_CHAT_ID, admin_note, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# ----------------------------------------------------
# 📝 5. NEW REGISTRATION
# ----------------------------------------------------
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
            status = existing[0]
            if status == "Pending":
                bot.send_message(
                    message.chat.id, 
                    "⚠️ আপনার রেজিস্ট্রেশন অনুরোধ বর্তমানে পেন্ডিং (Pending) রয়েছে। এডমিন রিভিউ করার পর এপ্রুভ করবেন।", 
                    reply_markup=main_menu(tg_id)
                )
            else:
                bot.send_message(
                    message.chat.id, 
                    f"⚠️ আপনি ইতিমধ্যেই নিবন্ধিত মেম্বার! আপনার বর্তমান স্ট্যাটাস: `{status}`", 
                    parse_mode="Markdown", 
                    reply_markup=main_menu(tg_id)
                )
            return

        user_temp_data[tg_id] = {}
        msg = bot.send_message(
            message.chat.id, 
            "1️⃣ **Enter Your Facebook Profile Name:**", 
            parse_mode="Markdown", 
            reply_markup=cancel_keyboard()
        )
        bot.register_next_step_handler(msg, reg_get_fullname)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

def reg_get_fullname(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['fb_name'] = message.text.strip()
    msg = bot.send_message(
        message.chat.id, 
        "2️⃣ **Enter Your Full Name In English:**", 
        parse_mode="Markdown", 
        reply_markup=cancel_keyboard()
    )
    bot.register_next_step_handler(msg, reg_get_unique_id)

def reg_get_unique_id(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['full_name'] = message.text.strip()
    msg = bot.send_message(
        message.chat.id, 
        "3️⃣ **Enter Your Unique ID (Given by Team):**", 
        parse_mode="Markdown", 
        reply_markup=cancel_keyboard()
    )
    bot.register_next_step_handler(msg, reg_select_team)

def reg_select_team(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['unique_id'] = message.text.strip()

    msg = bot.send_message(
        message.chat.id, 
        "4️⃣ **Select Your Team:**", 
        reply_markup=teams_keyboard()
    )
    bot.register_next_step_handler(msg, reg_confirm)

def reg_confirm(message):
    is_cancelled, action = check_cancel_or_menu(message)
    if is_cancelled:
        if action != "cancel":
            handle_menu_action(message, action)
        return

    tg_id = message.from_user.id
    selected_team = message.text.strip()

    if selected_team not in TEAMS:
        bot.send_message(message.chat.id, "❌ অবৈধ টিম পছন্দ করা হয়েছে। রেজিস্ট্রেশন বাতিল হলো।", reply_markup=main_menu(tg_id))
        return

    data = user_temp_data.get(tg_id, {})
    data['team_name'] = selected_team
    data['user_type'] = "General Member"

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
            "✅ **Registration Request Submitted!**\n\nআপনার আবেদনটি এডমিন পেন্ডিংয়ে রাখা হয়েছে। অনুমোদন পেলে আপনাকে সিকিউরিটি কোড জানিয়ে দেওয়া হবে।",
            parse_mode="Markdown",
            reply_markup=main_menu(tg_id)
        )

        if ADMIN_CHAT_ID:
            admin_markup = InlineKeyboardMarkup()
            admin_markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"app_user_{tg_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_user_{tg_id}")
            )
            admin_alert = (
                f"📥 **নতুন রেজিস্ট্রেশন আবেদন!**\n\n"
                f"👤 **FB Name:** {data['fb_name']}\n"
                f"📛 **Full Name:** {data['full_name']}\n"
                f"🆔 **Unique ID:** {data['unique_id']}\n"
                f"🌐 **Team:** {data['team_name']}\n"
                f"🆔 **TG ID:** `{tg_id}`"
            )
            bot.send_message(ADMIN_CHAT_ID, admin_alert, parse_mode="Markdown", reply_markup=admin_markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ রেজিস্ট্রেশন ব্যর্থ হয়েছে (সম্ভবত এই Unique ID বা Telegram ID আগে ব্যবহার করা হয়েছে): {e}", reply_markup=main_menu(tg_id))

# ----------------------------------------------------
# 👑 6. ADMIN OPTIONS (Pending & Members List)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "⏳ Pending Registration")
def admin_pending_list_msg(message):
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        bot.send_message(message.chat.id, "❌ এই অপশনটি শুধুমাত্র মেইন এডমিনের জন্য।")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, unique_id, team_name FROM members WHERE status = 'Pending'")
        pending_users = cursor.fetchall()
        conn.close()

        if not pending_users:
            bot.send_message(message.chat.id, "✅ কোনো পেন্ডিং রেজিস্ট্রেশন আবেদন নেই।")
            return

        markup = InlineKeyboardMarkup()
        for u in pending_users:
            markup.add(InlineKeyboardButton(f"👤 {u['fb_name']} ({u['team_name']})", callback_data=f"pend_user_{u['telegram_id']}"))

        bot.send_message(message.chat.id, f"⏳ **পেন্ডিং আবেদনের তালিকা ({len(pending_users)} জন):**", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

@bot.message_handler(func=lambda msg: msg.text == "📋 Members List")
def admin_members_list_msg(message):
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        bot.send_message(message.chat.id, "❌ এই অপশনটি শুধুমাত্র মেইন এডমিনের জন্য।")
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team", callback_data="cat_info"),
        InlineKeyboardButton("🎭 Meme Team", callback_data="cat_meme")
    )
    bot.send_message(message.chat.id, "📋 **মেম্বার লিস্ট ক্যাটাগরি বেছে নিন:**", parse_mode="Markdown", reply_markup=markup)

# ----------------------------------------------------
# 🔘 CALLBACK QUERY HANDLER
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    data = call.data

    if data.startswith("pend_user_"):
        tg_id = int(data.replace("pend_user_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (tg_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            msg = (
                f"🔍 **Pending Request Details**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {u['fb_name']}\n"
                f"📛 **Full Name:** {u['full_name']}\n"
                f"🆔 **Unique ID:** {u['unique_id']}\n"
                f"🌐 **Team:** {u['team_name']}\n"
                f"🆔 **TG ID:** `{u['telegram_id']}`\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"app_user_{tg_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_user_{tg_id}")
            )
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="pending_list"))
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data == "pending_list":
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, unique_id, team_name FROM members WHERE status = 'Pending'")
        pending_users = cursor.fetchall()
        conn.close()

        if not pending_users:
            bot.edit_message_text("✅ কোনো পেন্ডিং রেজিস্ট্রেশন আবেদন নেই।", call.message.chat.id, call.message.message_id)
            return

        markup = InlineKeyboardMarkup()
        for u in pending_users:
            markup.add(InlineKeyboardButton(f"👤 {u['fb_name']} ({u['team_name']})", callback_data=f"pend_user_{u['telegram_id']}"))

        bot.edit_message_text(f"⏳ **পেন্ডিং আবেদনের তালিকা ({len(pending_users)} জন):**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("app_user_"):
        tg_id = int(data.replace("app_user_", ""))
        conn = get_db_connection()
        code = generate_security_code(conn)
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s", (code, tg_id))
        conn.commit()

        cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (tg_id,))
        mem = cursor.fetchone()
        conn.close()

        bot.edit_message_text(f"✅ **{mem[0]}**-এর আবেদন সফলভাবে এপ্রুভ করা হয়েছে!\n🔑 সিকিউরিটি কোড: `{code}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

        try:
            approve_msg = (
                f"🎉 **রেজিস্ট্রেশন অনুমোদন সফল হয়েছে!**\n\n"
                f"স্বাগতম **{mem[0]}**!\n"
                f"🌐 **টিম:** {mem[1]}\n"
                f"🔑 **আপনার সিকিউরিটি কোড:** `{code}`\n\n"
                f"⚠️ *এই সিকিউরিটি কোডটি কোথাও সেভ করে রাখুন। পরবর্তীতে অ্যাকাউন্ট রিকভারিতে লাগবে।*"
            )
            bot.send_message(tg_id, approve_msg, parse_mode="Markdown")
        except Exception:
            pass

    elif data.startswith("rej_user_"):
        tg_id = int(data.replace("rej_user_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        conn.commit()
        conn.close()

        bot.edit_message_text("❌ রেজিস্ট্রেশন আবেদনটি বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

        try:
            bot.send_message(tg_id, "❌ দুঃখিত, আপনার রেজিস্ট্রেশন আবেদনটি বাতিল করা হয়েছে।")
        except Exception:
            pass

    elif data == "cat_back_main":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("ℹ️ Info Team", callback_data="cat_info"),
            InlineKeyboardButton("🎭 Meme Team", callback_data="cat_meme")
        )
        bot.edit_message_text("📋 **মেম্বার লিস্ট ক্যাটাগরি বেছে নিন:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data == "cat_info":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Team Alpha", callback_data="team_alpha"),
            InlineKeyboardButton("Team Beta", callback_data="team_beta"),
            InlineKeyboardButton("Team Gamma", callback_data="team_gamma")
        )
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="cat_back_main"))
        bot.edit_message_text("ℹ️ **Info Team-এর সাব-টিম বেছে নিন:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data == "cat_meme":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Team Electron", callback_data="team_electron"),
            InlineKeyboardButton("Team Proton", callback_data="team_proton"),
            InlineKeyboardButton("Team Neutron", callback_data="team_neutron")
        )
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="cat_back_main"))
        bot.edit_message_text("🎭 **Meme Team-এর সাব-টিম বেছে নিন:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("team_"):
        slug = data.replace("team_", "")
        if slug in TEAM_SLUGS:
            team_name = TEAM_SLUGS[slug]
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT telegram_id, fb_name, full_name, unique_id FROM members WHERE team_name = %s AND status = 'Approved'", (team_name,))
            members = cursor.fetchall()
            conn.close()

            parent_cat = "cat_info" if slug in ["alpha", "beta", "gamma"] else "cat_meme"

            if not members:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔙 Back", callback_data=parent_cat))
                bot.edit_message_text(f"🌐 **{team_name}**-এ কোনো এপ্রুভড মেম্বার নেই।", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
                return

            markup = InlineKeyboardMarkup()
            for m in members:
                markup.add(InlineKeyboardButton(f"👤 {m['fb_name']} ({m['unique_id']})", callback_data=f"mem_detail_{m['telegram_id']}"))

            markup.add(InlineKeyboardButton("🔙 Back", callback_data=parent_cat))
            bot.edit_message_text(f"🌐 **{team_name}**-এর মেম্বারদের তালিকা ({len(members)} জন):\nকাঙ্ক্ষিত মেম্বারের বিস্তারিত দেখতে নামে ক্লিক করুন:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("mem_detail_"):
        tg_id = int(data.replace("mem_detail_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (tg_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            tg_username = "N/A"
            try:
                tg_user = bot.get_chat(tg_id)
                if tg_user.username:
                    tg_username = f"@{tg_user.username}"
            except Exception:
                pass

            reg_date = u['created_at'].strftime("%Y-%m-%d %H:%M") if u.get('created_at') else "N/A"

            msg_text = (
                f"📄 **Member Full Details**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {u['fb_name']}\n"
                f"📛 **Full Name:** {u['full_name']}\n"
                f"🆔 **Unique ID:** {u['unique_id']}\n"
                f"🌐 **Team:** {u['team_name']}\n"
                f"🆔 **TG ID:** `{u['telegram_id']}` ({tg_username})\n"
                f"🔑 **Security Code:** `{u['security_code']}`\n"
                f"📅 **Registration Date:** {reg_date}\n"
                f"⚡ **Status:** {u['status']}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )

            markup = InlineKeyboardMarkup()
            team_slug = [k for k, v in TEAM_SLUGS.items() if v == u['team_name']]
            back_target = f"team_{team_slug[0]}" if team_slug else "cat_back_main"
            markup.add(InlineKeyboardButton("🔙 Back to Team List", callback_data=back_target))

            bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

# ----------------------------------------------------
# 🚀 BOT & SERVER LAUNCH
# ----------------------------------------------------
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Registration Bot is Running...")
    bot.infinity_polling()
