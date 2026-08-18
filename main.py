import os
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ⚙️ Environment Variables (Render-এর সব ধরনের কী নেম গ্রহণ করবে)
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

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
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing in Render!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛠️ Auto DB Tables Setup
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE SEQUENCE IF NOT EXISTS security_code_seq START WITH 1;

            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                fb_name TEXT,
                full_name TEXT,
                unique_id TEXT,
                team_name TEXT,
                user_type TEXT,
                status TEXT DEFAULT 'Pending',
                security_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fb_name_requests (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                old_name TEXT,
                new_name TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS team_change_requests (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                old_team TEXT,
                requested_team TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

# 🏢 Teams & Categories Mapping
INFO_TEAMS = ["Team Alpha", "Team Beta", "Team Gamma"]
MEME_TEAMS = ["Team Electron", "Team Proton", "Team Neutron"]
TEAMS = INFO_TEAMS + MEME_TEAMS

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
        return f"KBKh2022{seq_val}"
    except Exception:
        conn.rollback()
        cursor.execute("SELECT COUNT(*) FROM members WHERE security_code IS NOT NULL")
        cnt = cursor.fetchone()[0] + 1
        return f"KBKh2022{cnt}"

# 🔍 User Status Checker
def get_user_status(tg_id):
    if ADMIN_CHAT_ID and str(tg_id).strip() == str(ADMIN_CHAT_ID).strip():
        return "ADMIN"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM members WHERE telegram_id = %s", (tg_id,))
        res = cursor.fetchone()
        conn.close()
        if res:
            return res[0]
        return "UNREGISTERED"
    except Exception as e:
        print(f"DB Error: {e}")
        return "UNREGISTERED"

# 📱 Keyboards
def main_menu(user_id):
    status = get_user_status(user_id)
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)

    if status == "ADMIN":
        markup.add(
            KeyboardButton("⏳ Pending Applications"),
            KeyboardButton("📋 Members List")
        )
    elif status == "Approved":
        markup.add(
            KeyboardButton("👤 My Profile"),
            KeyboardButton("🔄 Change FB Name"),
            KeyboardButton("🔄 Request Team Change")
        )
    elif status == "Pending":
        markup.add(
            KeyboardButton("🔄 Check Status / Refresh")
        )
    elif status == "Blocked":
        return None
    else:
        markup.add(
            KeyboardButton("📝 Register Now"),
            KeyboardButton("🔑 Already Registered?")
        )
    return markup

def cancel_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

def teams_keyboard():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)
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

# 🛑 Cancel Interceptor
def check_cancel_or_menu(message, retry_fn, retry_msg, retry_keyboard=None):
    text = message.text.strip() if message.text else ""
    tg_id = message.from_user.id

    if text in ["❌ Cancel", "/cancel"]:
        user_temp_data[tg_id] = user_temp_data.get(tg_id, {})
        user_temp_data[tg_id]['retry_fn'] = retry_fn
        user_temp_data[tg_id]['retry_msg'] = retry_msg
        user_temp_data[tg_id]['retry_keyboard'] = retry_keyboard

        confirm_markup = InlineKeyboardMarkup()
        confirm_markup.add(
            InlineKeyboardButton("✅ হ্যাঁ, বাতিল করুন", callback_data="confirm_cancel"),
            InlineKeyboardButton("❌ না, চালিয়ে যান", callback_data="deny_cancel")
        )
        bot.send_message(
            message.chat.id, 
            "⚠️ **আপনি কি নিশ্চিত যে প্রসেসটি বাতিল করতে চান?**", 
            parse_mode="Markdown", 
            reply_markup=confirm_markup
        )
        return True, "asking_cancel"

    menu_buttons = [
        "📝 Register Now", "🔄 Change FB Name", "🔑 Already Registered?", 
        "👤 My Profile", "🔄 Request Team Change", "⏳ Pending Applications", 
        "📋 Members List", "🔄 Check Status / Refresh"
    ]

    if text in menu_buttons:
        bot.clear_step_handler_by_chat_id(message.chat.id)
        handle_menu_action(message, text)
        return True, "switched_menu"

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
    elif action == "⏳ Pending Applications":
        admin_pending_applications(message)
    elif action == "📋 Members List":
        admin_members_list_msg(message)
    elif action == "🔄 Check Status / Refresh":
        check_status_refresh(message)

# ----------------------------------------------------
# 📌 /start Command
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "❌ **আপনাকে সিস্টেম থেকে ব্লক করা হয়েছে!**")
        return
    elif status == "ADMIN":
        text = "👑 **Admin Panel-এ আপনাকে স্বাগতম!**\n\nপেন্ডিং আবেদন বা মেম্বারদের তালিকা দেখতে নিচের অপশনগুলো ব্যবহার করুন।"
    elif status == "Approved":
        text = "👋 **KBKh Science Ecosystem-এ আপনাকে স্বাগতম!**\n\nআপনি একজন এপ্রুভড মেম্বার।"
    elif status == "Pending":
        text = "⏳ **আপনার রেজিস্ট্রেশন আবেদনটি পেন্ডিং অবস্থায় আছে!**"
    else:
        text = "👋 **KBKh Science Ecosystem-এ আপনাকে স্বাগতম!**\n\nরেজিস্ট্রেশন করতে `📝 Register Now` চাপুন।"

    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu(tg_id))

# 🔄 Refresh Status Button
@bot.message_handler(func=lambda msg: msg.text == "🔄 Check Status / Refresh")
def check_status_refresh(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status == "Approved":
        bot.send_message(message.chat.id, "🎉 **অভিনন্দন!** আপনার আবেদন অনুমোদন করা হয়েছে।", parse_mode="Markdown", reply_markup=main_menu(tg_id))
    elif status == "Pending":
        bot.send_message(message.chat.id, "⏳ আপনার আবেদন এখনও পেন্ডিং রয়েছে।", reply_markup=main_menu(tg_id))
    else:
        bot.send_message(message.chat.id, "❌ আপনি নিবন্ধিত নন।", reply_markup=main_menu(tg_id))

# 👑 1. ADMIN PENDING APPLICATIONS
@bot.message_handler(func=lambda msg: msg.text == "⏳ Pending Applications")
def admin_pending_applications(message):
    tg_id = message.from_user.id
    if str(tg_id).strip() != str(ADMIN_CHAT_ID).strip():
        bot.send_message(message.chat.id, "❌ এই অপশনটি শুধুমাত্র এডমিনের জন্য।")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, unique_id, team_name FROM members WHERE status = 'Pending'")
        pending_users = cursor.fetchall()
        conn.close()

        if not pending_users:
            bot.send_message(message.chat.id, "✅ কোনো পেন্ডিং রেজিস্ট্রেশন আবেদন নেই।", reply_markup=main_menu(tg_id))
            return

        markup = InlineKeyboardMarkup()
        for u in pending_users:
            markup.add(InlineKeyboardButton(f"👤 {u['fb_name']} ({u['team_name']})", callback_data=f"pend_user_{u['telegram_id']}"))

        bot.send_message(
            message.chat.id, 
            f"📝 **পেন্ডিং রেজিস্ট্রেশন আবেদন ({len(pending_users)} জন):**\nনিচে ক্লিক করে এপ্রুভ বা রিজেক্ট করুন:", 
            parse_mode="Markdown", 
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}", reply_markup=main_menu(tg_id))

# 👤 2. MY PROFILE
@bot.message_handler(func=lambda msg: msg.text == "👤 My Profile")
def view_profile(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "❌ আপনার রেজিস্ট্রেশন এপ্রুভড হওয়ার পরই কেবল প্রোফাইল দেখতে পাবেন!", reply_markup=main_menu(tg_id))
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, status, security_code FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            fb_name, full_name, unique_id, team, u_status, code = user
            code_display = f"`{code}`" if code else "*(Approved হওয়ার পর পাবেন)*"

            profile_msg = (
                f"👤 **Your KBKh Profile Summary**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {fb_name}\n"
                f"📛 **Full Name:** {full_name}\n"
                f"🆔 **Unique ID:** {unique_id}\n"
                f"🌐 **Team:** {team}\n"
                f"⚡ **Status:** {u_status}\n"
                f"🔑 **Security Code:** {code_display}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown", reply_markup=main_menu(tg_id))
        else:
            bot.send_message(message.chat.id, "❌ ডাটা পাওয়া যায়নি!", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# 🔄 3. CHANGE FB NAME (Spam Protected)
@bot.message_handler(func=lambda msg: msg.text == "🔄 Change FB Name")
def change_fb_name_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status != "Approved":
        bot.send_message(message.chat.id, "❌ আপনার আবেদন এপ্রুভড হওয়ার পরই নাম পরিবর্তন করতে পারবেন।", reply_markup=main_menu(tg_id))
        return

    # 🚫 Check for existing Pending Request
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM fb_name_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        pending_req = cursor.fetchone()
        conn.close()

        if pending_req:
            bot.send_message(message.chat.id, "⚠️ **আপনার একটি ফেসবুক নাম পরিবর্তনের আবেদন ইতিমধ্যেই পেন্ডিং রয়েছে!**\nএডমিন সেটি প্রসেস না করা পর্যন্ত পুনরায় আবেদন করা যাবে না।", parse_mode="Markdown", reply_markup=main_menu(tg_id))
            return
    except Exception as e:
        print(f"Check Pending FB Name Error: {e}")

    msg = bot.send_message(message.chat.id, "✏️ **Enter your new Facebook Profile Name:**", parse_mode="Markdown", reply_markup=cancel_keyboard())
    bot.register_next_step_handler(msg, process_fb_name_change)

def process_fb_name_change(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=process_fb_name_change, retry_msg="✏️ **Enter your new Facebook Profile Name:**", retry_keyboard=cancel_keyboard())
    if is_intercepted:
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
            cursor.execute("INSERT INTO fb_name_requests (telegram_id, old_name, new_name, status) VALUES (%s, %s, %s, 'Pending') RETURNING id", (tg_id, old_fb_name, new_fb_name))
            req_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            bot.send_message(message.chat.id, f"✅ **আপনার নাম পরিবর্তনের আবেদন এডমিনের কাছে পাঠানো হয়েছে!**\n\n**বর্তমান নাম:** {old_fb_name}\n**নতুন নাম:** {new_fb_name}", parse_mode="Markdown", reply_markup=main_menu(tg_id))

            if ADMIN_CHAT_ID:
                admin_markup = InlineKeyboardMarkup()
                admin_markup.add(
                    InlineKeyboardButton("✅ Approve", callback_data=f"app_fbreq_{req_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"rej_fbreq_{req_id}")
                )
                admin_note = f"✏️ **FB Name Change Request!**\n\n👤 **Old Name:** {old_fb_name}\n✨ **New Name:** {new_fb_name}\n🌐 **Team:** {team}\n🆔 **TG ID:** `{tg_id}`"
                bot.send_message(ADMIN_CHAT_ID, admin_note, parse_mode="Markdown", reply_markup=admin_markup)
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ডাটা পাওয়া যায়নি!", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# 🔑 4. ALREADY REGISTERED?
@bot.message_handler(func=lambda msg: msg.text == "🔑 Already Registered?")
def recovery_start(message):
    msg = bot.send_message(message.chat.id, "🔑 **Enter your Security Code:**", parse_mode="Markdown", reply_markup=cancel_keyboard())
    bot.register_next_step_handler(msg, process_recovery)

def process_recovery(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=process_recovery, retry_msg="🔑 **Enter your Security Code:**", retry_keyboard=cancel_keyboard())
    if is_intercepted:
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

            success_msg = f"🎉 **Account Restored Successfully!**\n\n👤 **FB Name:** {fb_name}\n📛 **Full Name:** {full_name}\n🆔 **Unique ID:** {unique_id}\n🌐 **Team:** {team}"
            bot.send_message(message.chat.id, success_msg, parse_mode="Markdown", reply_markup=main_menu(new_tg_id))
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ ভুল সিকিউরিটি কোড! সঠিক কোড দিয়ে আবার চেষ্টা করুন।", reply_markup=main_menu(new_tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(new_tg_id))

# 🔄 5. REQUEST TEAM CHANGE (Spam Protected)
@bot.message_handler(func=lambda msg: msg.text == "🔄 Request Team Change")
def team_change_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status != "Approved":
        bot.send_message(message.chat.id, "❌ আপনার আবেদন এপ্রুভড হওয়ার পরই টিম পরিবর্তনের অনুরোধ করতে পারবেন।", reply_markup=main_menu(tg_id))
        return

    # 🚫 Check for existing Pending Request
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM team_change_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        pending_req = cursor.fetchone()

        if pending_req:
            conn.close()
            bot.send_message(message.chat.id, "⚠️ **আপনার একটি টিম পরিবর্তনের আবেদন ইতিমধ্যেই পেন্ডিং রয়েছে!**\nএডমিন সেটি প্রসেস না করা পর্যন্ত পুনরায় আবেদন করা যাবে না।", parse_mode="Markdown", reply_markup=main_menu(tg_id))
            return

        cursor.execute("SELECT team_name FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            bot.send_message(message.chat.id, "❌ ডাটা পাওয়া যায়নি!", reply_markup=main_menu(tg_id))
            return

        user_temp_data[tg_id] = {'old_team': user[0]}
        msg = bot.send_message(message.chat.id, f"🌐 আপনার বর্তমান টিম: **{user[0]}**\n\nনতুন কোন টিমে যুক্ত হতে চান তা সিলেক্ট করুন:", parse_mode="Markdown", reply_markup=teams_keyboard())
        bot.register_next_step_handler(msg, process_team_change_request)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

def process_team_change_request(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=process_team_change_request, retry_msg="🌐 নতুন কোন টিমে যুক্ত হতে চান তা সিলেক্ট করুন:", retry_keyboard=teams_keyboard())
    if is_intercepted:
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
        cursor.execute("INSERT INTO team_change_requests (telegram_id, old_team, requested_team, status) VALUES (%s, %s, %s, 'Pending') RETURNING id", (tg_id, old_team, requested_team))
        req_id = cursor.fetchone()[0]
        conn.commit()

        cursor.execute("SELECT fb_name FROM members WHERE telegram_id = %s", (tg_id,))
        fb_name = cursor.fetchone()[0]
        conn.close()

        bot.send_message(message.chat.id, f"✅ **টিম পরিবর্তনের আবেদন জমা হয়েছে!**\n**{old_team}** ➔ **{requested_team}**", parse_mode="Markdown", reply_markup=main_menu(tg_id))

        if ADMIN_CHAT_ID:
            admin_markup = InlineKeyboardMarkup()
            admin_markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"app_tmreq_{req_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_tmreq_{req_id}")
            )
            admin_note = f"🔄 **Team Change Request!**\n\n👤 **Member:** {fb_name}\n🌐 **Old Team:** {old_team}\n➡️ **Requested Team:** {requested_team}\n🆔 **TG ID:** `{tg_id}`"
            bot.send_message(ADMIN_CHAT_ID, admin_note, parse_mode="Markdown", reply_markup=admin_markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ত্রুটি: {e}", reply_markup=main_menu(tg_id))

# 📝 6. NEW REGISTRATION
@bot.message_handler(func=lambda msg: msg.text == "📝 Register Now")
def reg_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Pending":
        bot.send_message(message.chat.id, "⚠️ আপনার রেজিস্ট্রেশন অনুরোধ ইতিমধ্যেই পেন্ডিং রয়েছে।", reply_markup=main_menu(tg_id))
        return
    elif status == "Approved":
        bot.send_message(message.chat.id, "✅ আপনি ইতিমধ্যেই নিবন্ধিত মেম্বার!", reply_markup=main_menu(tg_id))
        return

    user_temp_data[tg_id] = {}
    msg = bot.send_message(message.chat.id, "1️⃣ **Enter Your Facebook Profile Name:**", parse_mode="Markdown", reply_markup=cancel_keyboard())
    bot.register_next_step_handler(msg, reg_get_fullname)

def reg_get_fullname(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=reg_get_fullname, retry_msg="1️⃣ **Enter Your Facebook Profile Name:**", retry_keyboard=cancel_keyboard())
    if is_intercepted:
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['fb_name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "2️⃣ **Enter Your Full Name In English:**", parse_mode="Markdown", reply_markup=cancel_keyboard())
    bot.register_next_step_handler(msg, reg_get_unique_id)

def reg_get_unique_id(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=reg_get_unique_id, retry_msg="2️⃣ **Enter Your Full Name In English:**", retry_keyboard=cancel_keyboard())
    if is_intercepted:
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['full_name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "3️⃣ **Enter Your Unique ID (Given by Team):**", parse_mode="Markdown", reply_markup=cancel_keyboard())
    bot.register_next_step_handler(msg, reg_select_team)

def reg_select_team(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=reg_select_team, retry_msg="3️⃣ **Enter Your Unique ID (Given by Team):**", retry_keyboard=cancel_keyboard())
    if is_intercepted:
        return

    tg_id = message.from_user.id
    user_temp_data[tg_id]['unique_id'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "4️⃣ **Select Your Team:**", reply_markup=teams_keyboard())
    bot.register_next_step_handler(msg, reg_confirm)

def reg_confirm(message):
    is_intercepted, reason = check_cancel_or_menu(message, retry_fn=reg_confirm, retry_msg="4️⃣ **Select Your Team:**", retry_keyboard=teams_keyboard())
    if is_intercepted:
        return

    tg_id = message.from_user.id
    selected_team = message.text.strip()

    if selected_team not in TEAMS:
        bot.send_message(message.chat.id, "❌ অবৈধ টিম পছন্দ করা হয়েছে।", reply_markup=main_menu(tg_id))
        return

    data = user_temp_data.get(tg_id, {})
    data['team_name'] = selected_team
    data['user_type'] = "General Member"
    unique_id = data.get('unique_id', '').strip()

    cat_teams = INFO_TEAMS if selected_team in INFO_TEAMS else MEME_TEAMS
    cat_name = "Info Team" if selected_team in INFO_TEAMS else "Meme Team"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM members WHERE LOWER(unique_id) = LOWER(%s) AND team_name = ANY(%s)", (unique_id, cat_teams))
        exists_count = cursor.fetchone()[0]

        if exists_count > 0:
            conn.close()
            bot.send_message(message.chat.id, f"⚠️ **এই Unique ID-টি ({unique_id}) `{cat_name}` ক্যাটাগরিতে ইতিমধ্যেই ব্যবহৃত হয়েছে!**", parse_mode="Markdown", reply_markup=main_menu(tg_id))
            return

        cursor.execute("INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", (tg_id, data.get('fb_name', ''), data.get('full_name', ''), unique_id, data['team_name'], data['user_type']))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, "✅ **Registration Request Submitted!**\n\nআপনার আবেদনটি এডমিন পেন্ডিংয়ে রাখা হয়েছে।", parse_mode="Markdown", reply_markup=main_menu(tg_id))

        if ADMIN_CHAT_ID:
            admin_markup = InlineKeyboardMarkup()
            admin_markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"app_user_{tg_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_user_{tg_id}")
            )
            admin_alert = f"📥 **নতুন রেজিস্ট্রেশন আবেদন!**\n\n👤 **FB Name:** {data.get('fb_name', '')}\n📛 **Full Name:** {data.get('full_name', '')}\n🆔 **Unique ID:** {unique_id}\n🌐 **Team:** {data['team_name']}\n🆔 **TG ID:** `{tg_id}`"
            bot.send_message(ADMIN_CHAT_ID, admin_alert, parse_mode="Markdown", reply_markup=admin_markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ রেজিস্ট্রেশন ব্যর্থ হয়েছে: {e}", reply_markup=main_menu(tg_id))

# 📋 7. MEMBERS LIST
@bot.message_handler(func=lambda msg: msg.text == "📋 Members List")
def admin_members_list_msg(message):
    if str(message.from_user.id).strip() != str(ADMIN_CHAT_ID).strip():
        bot.send_message(message.chat.id, "❌ এই অপশনটি শুধুমাত্র এডমিনের জন্য।")
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team", callback_data="cat_info"),
        InlineKeyboardButton("🎭 Meme Team", callback_data="cat_meme")
    )
    bot.send_message(message.chat.id, "📋 **মেম্বার লিস্ট ক্যাটাগরি বেছে নিন:**", parse_mode="Markdown", reply_markup=markup)

# 🔘 CALLBACK QUERY HANDLER (Fixed Freeze & Missing Handlers)
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    data = call.data
    tg_id = call.from_user.id

    if data == "confirm_cancel":
        user_temp_data.pop(tg_id, None)
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        bot.edit_message_text("❌ প্রসেসটি বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "প্রধান মেনু:", reply_markup=main_menu(tg_id))

    elif data == "deny_cancel":
        bot.edit_message_text("▶️ প্রসেসটি পুনরায় চালু রয়েছে।", call.message.chat.id, call.message.message_id)
        u_info = user_temp_data.get(tg_id, {})
        retry_fn = u_info.get('retry_fn')
        retry_msg = u_info.get('retry_msg', 'অনুগ্রহ করে তথ্য লিখুন:')
        retry_kb = u_info.get('retry_keyboard')

        if retry_fn:
            msg = bot.send_message(call.message.chat.id, retry_msg, parse_mode="Markdown", reply_markup=retry_kb)
            bot.register_next_step_handler(msg, retry_fn)

    elif data.startswith("pend_user_"):
        target_id = int(data.replace("pend_user_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (target_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            msg_text = f"🔍 **Pending Registration Request**\n━━━━━━━━━━━━━━━━━━\n👥 **FB Name:** {u['fb_name']}\n📛 **Full Name:** {u['full_name']}\n🆔 **Unique ID:** {u['unique_id']}\n🌐 **Team:** {u['team_name']}\n🆔 **TG ID:** `{u['telegram_id']}`\n━━━━━━━━━━━━━━━━━━"
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"app_user_{target_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_user_{target_id}")
            )
            bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("app_user_"):
        target_id = int(data.replace("app_user_", ""))
        conn = get_db_connection()
        code = generate_security_code(conn)
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s", (code, target_id))
        conn.commit()

        cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (target_id,))
        mem = cursor.fetchone()
        conn.close()

        if mem:
            bot.edit_message_text(f"✅ **{mem[0]}**-এর আবেদন সফলভাবে এপ্রুভ করা হয়েছে!\n🔑 সিকিউরিটি কোড: `{code}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

            try:
                bot.send_message(target_id, f"🎉 **রেজিস্ট্রেশন অনুমোদন সফল হয়েছে!**\n\nস্বাগতম **{mem[0]}**!\n🌐 **টিম:** {mem[1]}\n🔑 **আপনার সিকিউরিটি কোড:** `{code}`", parse_mode="Markdown", reply_markup=main_menu(target_id))
            except Exception:
                pass

    elif data.startswith("rej_user_"):
        target_id = int(data.replace("rej_user_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE telegram_id = %s AND status = 'Pending'", (target_id,))
        conn.commit()
        conn.close()

        bot.edit_message_text("❌ রেজিস্ট্রেশন আবেদনটি বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

        try:
            bot.send_message(target_id, "❌ দুঃখিত, আপনার রেজিস্ট্রেশন আবেদনটি বাতিল করা হয়েছে।", reply_markup=main_menu(target_id))
        except Exception:
            pass

    # ✏️ FB Name Change Request Approve/Reject Handlers
    elif data.startswith("app_fbreq_"):
        req_id = int(data.replace("app_fbreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, new_name FROM fb_name_requests WHERE id = %s AND status = 'Pending'", (req_id,))
        req = cursor.fetchone()
        if req:
            u_tg_id, new_name = req
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (new_name, u_tg_id))
            cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s", (req_id,))
            conn.commit()
            bot.edit_message_text(f"✅ FB নাম পরিবর্তন এপ্রুভড! (নতুন নাম: **{new_name}**)", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            try:
                bot.send_message(u_tg_id, f"🎉 আপনার FB নাম পরিবর্তনের আবেদন অনুমোদিত হয়েছে!\n**নতুন নাম:** {new_name}", parse_mode="Markdown", reply_markup=main_menu(u_tg_id))
            except Exception:
                pass
        else:
            bot.edit_message_text("⚠️ এই আবেদনটি ইতিমধ্যেই প্রসেস করা হয়েছে।", call.message.chat.id, call.message.message_id)
        conn.close()

    elif data.startswith("rej_fbreq_"):
        req_id = int(data.replace("rej_fbreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM fb_name_requests WHERE id = %s AND status = 'Pending'", (req_id,))
        req = cursor.fetchone()
        if req:
            u_tg_id = req[0]
            cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
            conn.commit()
            bot.edit_message_text("❌ FB নাম পরিবর্তনের আবেদন বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)
            try:
                bot.send_message(u_tg_id, "❌ আপনার FB নাম পরিবর্তনের আবেদনটি বাতিল করা হয়েছে।", reply_markup=main_menu(u_tg_id))
            except Exception:
                pass
        else:
            bot.edit_message_text("⚠️ এই আবেদনটি ইতিমধ্যেই প্রসেস করা হয়েছে।", call.message.chat.id, call.message.message_id)
        conn.close()

    # 🔄 Team Change Request Approve/Reject Handlers
    elif data.startswith("app_tmreq_"):
        req_id = int(data.replace("app_tmreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, requested_team FROM team_change_requests WHERE id = %s AND status = 'Pending'", (req_id,))
        req = cursor.fetchone()
        if req:
            u_tg_id, new_team = req
            cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s", (new_team, u_tg_id))
            cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s", (req_id,))
            conn.commit()
            bot.edit_message_text(f"✅ টিম পরিবর্তন এপ্রুভড! (নতুন টিম: **{new_team}**)", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            try:
                bot.send_message(u_tg_id, f"🎉 আপনার টিম পরিবর্তনের আবেদন অনুমোদিত হয়েছে!\n**নতুন টিম:** {new_team}", parse_mode="Markdown", reply_markup=main_menu(u_tg_id))
            except Exception:
                pass
        else:
            bot.edit_message_text("⚠️ এই আবেদনটি ইতিমধ্যেই প্রসেস করা হয়েছে।", call.message.chat.id, call.message.message_id)
        conn.close()

    elif data.startswith("rej_tmreq_"):
        req_id = int(data.replace("rej_tmreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM team_change_requests WHERE id = %s AND status = 'Pending'", (req_id,))
        req = cursor.fetchone()
        if req:
            u_tg_id = req[0]
            cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
            conn.commit()
            bot.edit_message_text("❌ টিম পরিবর্তনের আবেদন বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)
            try:
                bot.send_message(u_tg_id, "❌ আপনার টিম পরিবর্তনের আবেদনটি বাতিল করা হয়েছে।", reply_markup=main_menu(u_tg_id))
            except Exception:
                pass
        else:
            bot.edit_message_text("⚠️ এই আবেদনটি ইতিমধ্যেই প্রসেস করা হয়েছে।", call.message.chat.id, call.message.message_id)
        conn.close()

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
            bot.edit_message_text(f"🌐 **{team_name}**-এর মেম্বারদের তালিকা ({len(members)} জন):", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("mem_detail_"):
        target_id = int(data.replace("mem_detail_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (target_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            tg_username = "N/A"
            try:
                tg_user = bot.get_chat(target_id)
                if tg_user.username:
                    tg_username = f"@{tg_user.username}"
            except Exception:
                pass

            reg_date = u['created_at'].strftime("%Y-%m-%d %H:%M") if u.get('created_at') else "N/A"

            msg_text = (
                f"📄 **Member Full Details**\n━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {u['fb_name']}\n"
                f"📛 **Full Name:** {u['full_name']}\n"
                f"🆔 **Unique ID:** {u['unique_id']}\n"
                f"🌐 **Team:** {u['team_name']}\n"
                f"🆔 **TG ID:** `{u['telegram_id']}` ({tg_username})\n"
                f"🔑 **Security Code:** `{u['security_code']}`\n"
                f"📅 **Registration Date:** {reg_date}\n"
                f"⚡ **Status:** {u['status']}\n━━━━━━━━━━━━━━━━━━"
            )

            markup = InlineKeyboardMarkup()
            team_slug = [k for k, v in TEAM_SLUGS.items() if v == u['team_name']]
            back_target = f"team_{team_slug[0]}" if team_slug else "cat_back_main"
            markup.add(InlineKeyboardButton("🔙 Back to Team List", callback_data=back_target))

            bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

# 🚀 BOT LAUNCH
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Registration Bot is Running...")
    bot.infinity_polling()
