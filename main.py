import os
import time
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ⚙️ Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Server for Keep Alive
app = Flask('')

@app.route('/')
def home():
    return "KBKh Registration Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# 🔌 Database Connection Helper
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛠️ Auto DB Tables Setup & Sync with Bot Control Room
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
                user_type TEXT DEFAULT 'General Member',
                status TEXT DEFAULT 'Pending',
                security_code TEXT,
                is_blocked BOOLEAN DEFAULT FALSE,
                is_removed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Ensure columns exist if table was created previously without them
            ALTER TABLE members ADD COLUMN IF NOT EXISTS id SERIAL;
            ALTER TABLE members ADD COLUMN IF NOT EXISTS user_type TEXT DEFAULT 'General Member';
            ALTER TABLE members ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Pending';
            ALTER TABLE members ADD COLUMN IF NOT EXISTS security_code TEXT;
            ALTER TABLE members ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;
            ALTER TABLE members ADD COLUMN IF NOT EXISTS is_removed BOOLEAN DEFAULT FALSE;
            ALTER TABLE members ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

            -- Fix NULL values for Control Room Compatibility
            UPDATE members SET is_blocked = FALSE WHERE is_blocked IS NULL;
            UPDATE members SET is_removed = FALSE WHERE is_removed IS NULL;

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
        print("DB Initialized & Synchronized Successfully!")
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

# 🏢 Teams Mapping
INFO_TEAMS = ["Alpha", "Beta", "Gamma"]
MEME_TEAMS = ["Electron", "Proton", "Neutron"]
TEAMS = INFO_TEAMS + MEME_TEAMS

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
        cursor.execute("SELECT status, is_blocked, is_removed FROM members WHERE telegram_id = %s", (tg_id,))
        res = cursor.fetchone()
        conn.close()
        if res:
            status, is_blocked, is_removed = res[0], res[1], res[2]
            if is_blocked or status == "Blocked":
                return "Blocked"
            if is_removed or status == "Removed":
                return "UNREGISTERED"
            return status
        return "UNREGISTERED"
    except Exception as e:
        print(f"DB Error: {e}")
        return "UNREGISTERED"

# 📱 Main Keyboards Helper
def main_menu(user_id):
    status = get_user_status(user_id)
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)

    if status == "ADMIN":
        markup.add(
            KeyboardButton("Pending Applications"),
            KeyboardButton("Members List")
        )
    elif status == "Approved":
        markup.add(
            KeyboardButton("My Profile"),
            KeyboardButton("Change Fb Name")
        )
        markup.add(
            KeyboardButton("Request Team Change")
        )
    elif status == "Pending":
        markup.add(
            KeyboardButton("Refresh Status 🔄")
        )
    elif status == "Blocked":
        return None
    else:
        markup.add(
            KeyboardButton("Register Now"),
            KeyboardButton("Already Registered")
        )
    return markup

def cancel_keyboard(show_back=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    if show_back:
        markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))
    else:
        markup.add(KeyboardButton("Cancel"))
    return markup

def inline_cancel_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Cancel ❌", callback_data="cancel_reg_inline"))
    return markup

def team_select_keyboard():
    markup = ReplyKeyboardMarkup(row_width=3, resize_keyboard=True, one_time_keyboard=False)
    markup.add(
        KeyboardButton("Alpha"), KeyboardButton("Beta"), KeyboardButton("Gamma"),
        KeyboardButton("Electron"), KeyboardButton("Proton"), KeyboardButton("Neutron")
    )
    markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))
    return markup

# 🛑 Immediate Direct Cancel Helper (No Permission Dialog)
def direct_cancel(message):
    tg_id = message.from_user.id
    user_temp_data.pop(tg_id, None)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    bot.send_message(message.chat.id, "Process Cancelled✅", reply_markup=main_menu(tg_id))

# 📌 /start Command Handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_temp_data.pop(tg_id, None)

    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status == "ADMIN":
        bot.send_message(message.chat.id, "Welcome Admin Panel", reply_markup=main_menu(tg_id))
    elif status == "Approved":
        bot.send_message(message.chat.id, "Welcome to KBKh Science Ecosystem", reply_markup=main_menu(tg_id))
    elif status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
    else:
        bot.send_message(message.chat.id, "Welcome to KBKh Bot Ecosystem. Please Registration Now!", reply_markup=main_menu(tg_id))

# 🔄 Refresh Status Button Handler
@bot.message_handler(func=lambda msg: msg.text == "Refresh Status 🔄")
def check_status_refresh(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status == "Approved":
        bot.send_message(message.chat.id, "Registration approval was successful!✅", reply_markup=main_menu(tg_id))
    elif status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
    else:
        bot.send_message(message.chat.id, "You are not registered", reply_markup=main_menu(tg_id))

# 📝 REGISTRATION FLOW
@bot.message_handler(func=lambda msg: msg.text == "Register Now")
def reg_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return
    if status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
        return
    if status == "Approved":
        bot.send_message(message.chat.id, "You are already registered", reply_markup=main_menu(tg_id))
        return

    user_temp_data[tg_id] = {'flow': 'registration', 'step': 'fb_name'}
    msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_keyboard(show_back=False))
    bot.register_next_step_handler(msg, process_reg_steps)

def process_reg_steps(message):
    tg_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if text == "Cancel":
        direct_cancel(message)
        return

    data = user_temp_data.get(tg_id, {})
    step = data.get('step')

    if step == 'fb_name':
        data['fb_name'] = text
        data['step'] = 'full_name'
        user_temp_data[tg_id] = data
        msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=cancel_keyboard(show_back=True))
        bot.register_next_step_handler(msg, process_reg_steps)

    elif step == 'full_name':
        if text == "Back":
            data['step'] = 'fb_name'
            user_temp_data[tg_id] = data
            msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_keyboard(show_back=False))
            bot.register_next_step_handler(msg, process_reg_steps)
            return

        data['full_name'] = text
        data['step'] = 'unique_id'
        user_temp_data[tg_id] = data
        msg = bot.send_message(message.chat.id, "Enter Your Unique ID", reply_markup=cancel_keyboard(show_back=True))
        bot.register_next_step_handler(msg, process_reg_steps)

    elif step == 'unique_id':
        if text == "Back":
            data['step'] = 'full_name'
            user_temp_data[tg_id] = data
            msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=cancel_keyboard(show_back=True))
            bot.register_next_step_handler(msg, process_reg_steps)
            return

        data['unique_id'] = text
        data['step'] = 'select_team'
        user_temp_data[tg_id] = data
        msg = bot.send_message(message.chat.id, "Select Your Team", reply_markup=team_select_keyboard())
        bot.register_next_step_handler(msg, process_reg_steps)

    elif step == 'select_team':
        if text == "Back":
            data['step'] = 'unique_id'
            user_temp_data[tg_id] = data
            msg = bot.send_message(message.chat.id, "Enter Your Unique ID", reply_markup=cancel_keyboard(show_back=True))
            bot.register_next_step_handler(msg, process_reg_steps)
            return

        selected_team = text
        if selected_team not in TEAMS:
            msg = bot.send_message(message.chat.id, "Select Your Team", reply_markup=team_select_keyboard())
            bot.register_next_step_handler(msg, process_reg_steps)
            return

        unique_id = data.get('unique_id', '').strip()
        cat_teams = INFO_TEAMS if selected_team in INFO_TEAMS else MEME_TEAMS

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM members WHERE LOWER(unique_id) = LOWER(%s) AND team_name = ANY(%s) AND is_removed = FALSE AND status != 'Removed'", (unique_id, cat_teams))
            exists_count = cursor.fetchone()[0]
            conn.close()

            if exists_count > 0:
                data['step'] = 'unique_id'
                user_temp_data[tg_id] = data
                msg = bot.send_message(message.chat.id, "⚠️ Invalid Unique Id\n\nEnter Your Unique ID", reply_markup=cancel_keyboard(show_back=True))
                bot.register_next_step_handler(msg, process_reg_steps)
                return
        except Exception as e:
            print(f"Check Unique ID Error: {e}")

        data['team_name'] = selected_team
        data['step'] = 'confirm'
        user_temp_data[tg_id] = data

        summary_text = (
            f"👤Your KBKh Profile Summary\n\n"
            f"FB Name: {data.get('fb_name')}\n"
            f"Full Name: {data.get('full_name')}\n"
            f"Unique ID: {data.get('unique_id')}\n"
            f"Team: {selected_team}\n\n"
            f"Please recheck your final profile"
        )
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Submit", callback_data="submit_reg"),
            InlineKeyboardButton("Cancel", callback_data="cancel_reg_inline")
        )
        bot.send_message(message.chat.id, summary_text, reply_markup=markup)

# 🔑 ACCOUNT RECOVERY / ALREADY REGISTERED
@bot.message_handler(func=lambda msg: msg.text == "Already Registered")
def recovery_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    user_temp_data[tg_id] = {'flow': 'recovery'}
    msg = bot.send_message(message.chat.id, "Enter your security code to restore your account.", reply_markup=cancel_keyboard(show_back=False))
    bot.register_next_step_handler(msg, process_recovery)

def process_recovery(message):
    tg_id = message.from_user.id
    sec_code = message.text.strip() if message.text else ""

    if sec_code == "Cancel":
        direct_cancel(message)
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE security_code = %s AND is_blocked = FALSE AND is_removed = FALSE", (sec_code,))
        user = cursor.fetchone()

        if user:
            old_tg_id = user['telegram_id']

            cursor.execute("DELETE FROM members WHERE telegram_id = %s AND security_code IS DISTINCT FROM %s", (tg_id, sec_code))
            cursor.execute("DELETE FROM fb_name_requests WHERE telegram_id = %s", (tg_id,))
            cursor.execute("DELETE FROM team_change_requests WHERE telegram_id = %s", (tg_id,))

            cursor.execute("UPDATE members SET telegram_id = %s WHERE security_code = %s", (tg_id, sec_code))
            cursor.execute("UPDATE fb_name_requests SET telegram_id = %s WHERE telegram_id = %s", (tg_id, old_tg_id))
            cursor.execute("UPDATE team_change_requests SET telegram_id = %s WHERE telegram_id = %s", (tg_id, old_tg_id))
            conn.commit()
            conn.close()

            user_temp_data.pop(tg_id, None)
            success_text = f"Registration approval was successful!✅\n\nWelcome {user['full_name']}!\nTeam: {user['team_name']}\nYour Security Code: {sec_code}"
            bot.send_message(message.chat.id, success_text, reply_markup=main_menu(tg_id))
        else:
            conn.close()
            bot.send_message(message.chat.id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

# 👤 MY PROFILE
@bot.message_handler(func=lambda msg: msg.text == "My Profile")
def view_profile(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "You are not registered", reply_markup=main_menu(tg_id))
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, security_code FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if user:
            fb_name, full_name, unique_id, team, code = user
            profile_msg = (
                f"👤Your KBKh Profile Summary\n\n"
                f"FB Name: {fb_name}\n"
                f"Full Name: {full_name}\n"
                f"Unique ID: {unique_id}\n"
                f"Team: {team}\n"
                f"🫆Security Code: {code if code else ''}"
            )
            bot.send_message(message.chat.id, profile_msg, reply_markup=main_menu(tg_id))
        else:
            bot.send_message(message.chat.id, "Data not found", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

# 🔄 CHANGE FB NAME
@bot.message_handler(func=lambda msg: msg.text == "Change Fb Name")
def change_fb_name_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "You are not registered", reply_markup=main_menu(tg_id))
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM fb_name_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        pending_req = cursor.fetchone()
        conn.close()

        if pending_req:
            bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
            return
    except Exception as e:
        print(f"Check Pending FB Name Error: {e}")

    user_temp_data[tg_id] = {'flow': 'fb_name_change'}
    # Attach Inline Cancel button directly under text message
    msg = bot.send_message(message.chat.id, "Enter your new Facebook Profile Name:", reply_markup=inline_cancel_keyboard())
    bot.register_next_step_handler(msg, process_fb_name_change)

def process_fb_name_change(message):
    tg_id = message.from_user.id
    new_fb_name = message.text.strip() if message.text else ""

    if new_fb_name == "Cancel":
        direct_cancel(message)
        return

    user_temp_data[tg_id]['new_fb_name'] = new_fb_name

    summary_msg = (
        f"New Fb Name: {new_fb_name}\n\n"
        f"Click submit to confirm"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Submit", callback_data="submit_fb_name"),
        InlineKeyboardButton("Cancel", callback_data="cancel_reg_inline")
    )
    bot.send_message(message.chat.id, summary_msg, reply_markup=markup)

# 🔄 REQUEST TEAM CHANGE
@bot.message_handler(func=lambda msg: msg.text == "Request Team Change")
def team_change_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "You are not registered", reply_markup=main_menu(tg_id))
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM team_change_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        pending_req = cursor.fetchone()

        if pending_req:
            conn.close()
            bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
            return

        cursor.execute("SELECT team_name FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            bot.send_message(message.chat.id, "Data not found", reply_markup=main_menu(tg_id))
            return

        user_temp_data[tg_id] = {'flow': 'team_change', 'old_team': user[0], 'selected_team': None}
        send_team_change_inline_ui(message.chat.id, user[0], None)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

def send_team_change_inline_ui(chat_id, old_team, selected_team=None):
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    
    for t in TEAMS:
        label = f"🟢 {t}" if selected_team == t else (f"🔴 {t}" if t == old_team else t)
        buttons.append(InlineKeyboardButton(label, callback_data=f"sel_tm_{t}"))

    markup.add(*buttons[:3])
    markup.add(*buttons[3:])
    markup.add(
        InlineKeyboardButton("Submit", callback_data="submit_team_change"),
        InlineKeyboardButton("Cancel", callback_data="cancel_reg_inline")
    )
    bot.send_message(chat_id, "Select Team", reply_markup=markup)

# 👑 ADMIN: PENDING APPLICATIONS
@bot.message_handler(func=lambda msg: msg.text in ["Pending Applications", "Back to Applications Summary"])
def admin_pending_applications(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if str(tg_id).strip() != str(ADMIN_CHAT_ID).strip():
        bot.send_message(message.chat.id, "Admin access required")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'Pending' AND is_blocked = FALSE AND is_removed = FALSE")
        reg_cnt = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM fb_name_requests WHERE status = 'Pending'")
        fb_cnt = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM team_change_requests WHERE status = 'Pending'")
        tm_cnt = cursor.fetchone()[0]

        conn.close()

        markup = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        markup.add(
            KeyboardButton(f"Registration Application - {reg_cnt}"),
            KeyboardButton(f"Fb Name Change Application - {fb_cnt}"),
            KeyboardButton(f"Team Change Application - {tm_cnt}"),
            KeyboardButton("Cancel")
        )
        bot.send_message(message.chat.id, "Pending Applications Summary", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

@bot.message_handler(func=lambda msg: msg.text and (msg.text.startswith("Registration Application -") or msg.text.startswith("Fb Name Change Application -") or msg.text.startswith("Team Change Application -")))
def admin_show_pending_category(message):
    tg_id = message.from_user.id
    if str(tg_id).strip() != str(ADMIN_CHAT_ID).strip():
        return

    text = message.text

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        back_markup = ReplyKeyboardMarkup(resize_keyboard=True)
        back_markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))

        if text.startswith("Registration Application -"):
            cursor.execute("SELECT telegram_id, fb_name, full_name, unique_id, team_name FROM members WHERE status = 'Pending' AND is_blocked = FALSE AND is_removed = FALSE")
            regs = cursor.fetchall()
            conn.close()

            if not regs:
                bot.send_message(message.chat.id, "No pending registration applications.", reply_markup=back_markup)
                return

            for u in regs:
                card = (
                    f"👤New Registration:\n\n"
                    f"FB: {u['fb_name']}\n"
                    f"Full Name: {u['full_name']}\n"
                    f"ID: {u['unique_id']}\n"
                    f"Team: {u['team_name']}\n"
                    f"TG ID: {u['telegram_id']}"
                )
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_user_{u['telegram_id']}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_user_{u['telegram_id']}")
                )
                bot.send_message(message.chat.id, card, reply_markup=markup)

        elif text.startswith("Fb Name Change Application -"):
            cursor.execute("SELECT id, telegram_id, old_name, new_name FROM fb_name_requests WHERE status = 'Pending'")
            fbs = cursor.fetchall()
            conn.close()

            if not fbs:
                bot.send_message(message.chat.id, "No pending FB name change applications.", reply_markup=back_markup)
                return

            for f in fbs:
                card = (
                    f"FB Name Change Request:\n\n"
                    f"Old Name: {f['old_name']}\n"
                    f"New Name: {f['new_name']}\n"
                    f"TG ID: {f['telegram_id']}"
                )
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_fbreq_{f['id']}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_fbreq_{f['id']}")
                )
                bot.send_message(message.chat.id, card, reply_markup=markup)

        elif text.startswith("Team Change Application -"):
            cursor.execute("SELECT id, telegram_id, old_team, requested_team FROM team_change_requests WHERE status = 'Pending'")
            tms = cursor.fetchall()
            conn.close()

            if not tms:
                bot.send_message(message.chat.id, "No pending team change applications.", reply_markup=back_markup)
                return

            for t in tms:
                card = (
                    f"Team Change Request:\n\n"
                    f"Old Team: {t['old_team']}\n"
                    f"Requested Team: {t['requested_team']}\n"
                    f"TG ID: {t['telegram_id']}"
                )
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_tmreq_{t['id']}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_tmreq_{t['id']}")
                )
                bot.send_message(message.chat.id, card, reply_markup=markup)

        bot.send_message(message.chat.id, "End of pending list", reply_markup=back_markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")

# 📋 ADMIN: MEMBERS LIST
@bot.message_handler(func=lambda msg: msg.text == "Members List")
def admin_members_list_msg(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if str(tg_id).strip() != str(ADMIN_CHAT_ID).strip():
        bot.send_message(message.chat.id, "Admin access required")
        return

    markup = ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    markup.add(
        KeyboardButton("Alpha"), KeyboardButton("Beta"), KeyboardButton("Gamma"),
        KeyboardButton("Electron"), KeyboardButton("Proton"), KeyboardButton("Neutron")
    )
    markup.add(KeyboardButton("Cancel"))
    bot.send_message(message.chat.id, "Select Team to view members:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text in TEAMS)
def admin_show_team_members(message):
    tg_id = message.from_user.id
    if str(tg_id).strip() != str(ADMIN_CHAT_ID).strip():
        return

    team_name = message.text

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        # telegram_id used directly to eliminate missing 'id' column errors
        cursor.execute("SELECT telegram_id, fb_name, full_name, unique_id, team_name, security_code FROM members WHERE team_name = %s AND is_blocked = FALSE AND is_removed = FALSE", (team_name,))
        members = cursor.fetchall()
        conn.close()

        if not members:
            bot.send_message(message.chat.id, f"No members found in {team_name}.", reply_markup=cancel_keyboard(show_back=True))
            return

        markup = InlineKeyboardMarkup()
        for m in members:
            display_name = m['full_name'] or m['fb_name'] or str(m['telegram_id'])
            markup.add(InlineKeyboardButton(display_name, callback_data=f"view_mem_{m['telegram_id']}"))

        bot.send_message(message.chat.id, f"Members of {team_name}:", reply_markup=markup)
        bot.send_message(message.chat.id, "Navigation:", reply_markup=cancel_keyboard(show_back=True))

    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")

# 🔙 BACK & CANCEL GENERAL HANDLER
@bot.message_handler(func=lambda msg: msg.text in ["Back", "Cancel"])
def handle_back_or_cancel_text(message):
    tg_id = message.from_user.id
    text = message.text

    if text == "Cancel":
        direct_cancel(message)
    elif text == "Back":
        status = get_user_status(tg_id)
        if status == "ADMIN":
            admin_pending_applications(message)
        else:
            bot.send_message(message.chat.id, "Main Menu", reply_markup=main_menu(tg_id))

# 🔘 ALL CALLBACK QUERY HANDLERS
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    tg_id = call.from_user.id
    if get_user_status(tg_id) == "Blocked":
        try:
            bot.answer_callback_query(call.id, "Access Blocked⛔", show_alert=True)
        except Exception:
            pass
        return

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    data = call.data

    if data in ["cancel_reg_inline", "confirm_cancel_yes", "confirm_cancel_no"]:
        user_temp_data.pop(tg_id, None)
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        bot.edit_message_text("Process Cancelled✅", call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Main Menu", reply_markup=main_menu(tg_id))

    elif data == "submit_reg":
        u_data = user_temp_data.get(tg_id, {})
        if not u_data:
            bot.send_message(call.message.chat.id, "Session expired", reply_markup=main_menu(tg_id))
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE telegram_id = %s", (tg_id,))
            cursor.execute("DELETE FROM fb_name_requests WHERE telegram_id = %s", (tg_id,))
            cursor.execute("DELETE FROM team_change_requests WHERE telegram_id = %s", (tg_id,))

            cursor.execute(
                "INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status, is_blocked, is_removed) VALUES (%s, %s, %s, %s, %s, 'General Member', 'Pending', FALSE, FALSE)",
                (tg_id, u_data.get('fb_name'), u_data.get('full_name'), u_data.get('unique_id'), u_data.get('team_name'))
            )
            conn.commit()
            conn.close()

            user_temp_data.pop(tg_id, None)
            bot.edit_message_text("✅ Registration Request Submitted!\n\nYour application has been placed on admin pending!", call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))

            if ADMIN_CHAT_ID:
                admin_card = (
                    f"👤New Registration:\n\n"
                    f"FB: {u_data.get('fb_name')}\n"
                    f"Full Name: {u_data.get('full_name')}\n"
                    f"ID: {u_data.get('unique_id')}\n"
                    f"Team: {u_data.get('team_name')}\n"
                    f"TG ID: {tg_id}"
                )
                admin_markup = InlineKeyboardMarkup()
                admin_markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_user_{tg_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_user_{tg_id}")
                )
                bot.send_message(ADMIN_CHAT_ID, admin_card, reply_markup=admin_markup)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

    elif data == "submit_fb_name":
        u_data = user_temp_data.get(tg_id, {})
        new_name = u_data.get('new_fb_name')

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (tg_id,))
            u = cursor.fetchone()

            if u:
                old_name, team = u[0], u[1]
                cursor.execute("INSERT INTO fb_name_requests (telegram_id, old_name, new_name, status) VALUES (%s, %s, %s, 'Pending') RETURNING id", (tg_id, old_name, new_name))
                req_id = cursor.fetchone()[0]
                conn.commit()
                conn.close()

                user_temp_data.pop(tg_id, None)
                bot.edit_message_text("✅ FB Name Change Request Submitted!\n\nYour application has been placed on admin pending!", call.message.chat.id, call.message.message_id)

                if ADMIN_CHAT_ID:
                    admin_markup = InlineKeyboardMarkup()
                    admin_markup.add(
                        InlineKeyboardButton("Approve", callback_data=f"app_fbreq_{req_id}"),
                        InlineKeyboardButton("Reject", callback_data=f"rej_fbreq_{req_id}")
                    )
                    admin_note = f"FB Name Change Request:\n\nOld Name: {old_name}\nNew Name: {new_name}\nTeam: {team}\nTG ID: {tg_id}"
                    bot.send_message(ADMIN_CHAT_ID, admin_note, reply_markup=admin_markup)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

    elif data.startswith("sel_tm_"):
        sel_t = data.replace("sel_tm_", "")
        u_data = user_temp_data.get(tg_id, {})
        old_t = u_data.get('old_team')

        if sel_t == old_t:
            try:
                bot.answer_callback_query(call.id, f"You are already in {old_t}!", show_alert=True)
            except Exception:
                pass
            return

        u_data['selected_team'] = sel_t
        user_temp_data[tg_id] = u_data

        markup = InlineKeyboardMarkup(row_width=3)
        buttons = []
        for t in TEAMS:
            label = f"🟢 {t}" if sel_t == t else (f"🔴 {t}" if t == old_t else t)
            buttons.append(InlineKeyboardButton(label, callback_data=f"sel_tm_{t}"))

        markup.add(*buttons[:3])
        markup.add(*buttons[3:])
        markup.add(
            InlineKeyboardButton("Submit", callback_data="submit_team_change"),
            InlineKeyboardButton("Cancel", callback_data="cancel_reg_inline")
        )
        bot.edit_message_text("Select Team", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "submit_team_change":
        u_data = user_temp_data.get(tg_id, {})
        requested_team = u_data.get('selected_team')
        old_team = u_data.get('old_team')

        if not requested_team or requested_team == old_team:
            try:
                bot.answer_callback_query(call.id, "Please select a different team first!", show_alert=True)
            except Exception:
                pass
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

            user_temp_data.pop(tg_id, None)
            bot.edit_message_text("✅ Team Change Request Submitted!\n\nYour application has been placed on admin pending!", call.message.chat.id, call.message.message_id)

            if ADMIN_CHAT_ID:
                admin_markup = InlineKeyboardMarkup()
                admin_markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_tmreq_{req_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_tmreq_{req_id}")
                )
                admin_note = f"Team Change Request:\n\nMember: {fb_name}\nOld Team: {old_team}\nRequested Team: {requested_team}\nTG ID: {tg_id}"
                bot.send_message(ADMIN_CHAT_ID, admin_note, reply_markup=admin_markup)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

    elif data.startswith("app_user_"):
        target_id = int(data.replace("app_user_", ""))
        conn = get_db_connection()
        sec_code = generate_security_code(conn)
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s RETURNING full_name, team_name", (sec_code, target_id))
        u = cursor.fetchone()
        conn.commit()
        conn.close()

        bot.edit_message_text(f"Registration Approved for TG ID: {target_id}", call.message.chat.id, call.message.message_id)

        if u:
            full_name, team_name = u[0], u[1]
            user_msg = (
                f"Registration approval was successful!✅\n\n"
                f"Welcome {full_name}!\n"
                f"Team: {team_name}\n"
                f"Your Security Code: {sec_code}\n"
                f"⚠️Please do not share you security code with anyone."
            )
            try:
                bot.send_message(target_id, user_msg, reply_markup=main_menu(target_id))
            except Exception:
                pass

    elif data.startswith("rej_user_"):
        target_id = int(data.replace("rej_user_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE telegram_id = %s", (target_id,))
        conn.commit()
        conn.close()

        bot.edit_message_text(f"Registration Rejected for TG ID: {target_id}", call.message.chat.id, call.message.message_id)

        user_msg = "Registration Failed!❌\nPlease Try Again."
        try:
            bot.send_message(target_id, user_msg, reply_markup=main_menu(target_id))
        except Exception:
            pass

    elif data.startswith("app_fbreq_"):
        req_id = int(data.replace("app_fbreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM fb_name_requests WHERE id = %s", (req_id,))
        req = cursor.fetchone()

        if req:
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (req['new_name'], req['telegram_id']))
            cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s", (req_id,))
            conn.commit()

            bot.edit_message_text("FB Name Change Approved", call.message.chat.id, call.message.message_id)

            msg_to_user = f"Your request to change your FB Name has been approved✅\n\nNew FB Name: {req['new_name']}"
            try:
                bot.send_message(req['telegram_id'], msg_to_user, reply_markup=main_menu(req['telegram_id']))
            except Exception:
                pass
        conn.close()

    elif data.startswith("rej_fbreq_"):
        req_id = int(data.replace("rej_fbreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id FROM fb_name_requests WHERE id = %s", (req_id,))
        req = cursor.fetchone()

        if req:
            cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
            conn.commit()

            bot.edit_message_text("FB Name Change Rejected", call.message.chat.id, call.message.message_id)

            msg_to_user = "Your request to change your FB Name has been Failed❌"
            try:
                bot.send_message(req['telegram_id'], msg_to_user, reply_markup=main_menu(req['telegram_id']))
            except Exception:
                pass
        conn.close()

    elif data.startswith("app_tmreq_"):
        req_id = int(data.replace("app_tmreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM team_change_requests WHERE id = %s", (req_id,))
        req = cursor.fetchone()

        if req:
            cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s", (req['requested_team'], req['telegram_id']))
            cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s", (req_id,))
            conn.commit()

            bot.edit_message_text("Team Change Approved", call.message.chat.id, call.message.message_id)

            msg_to_user = f"Your request to change your Team has been approved✅\n\nNew Team: {req['requested_team']}"
            try:
                bot.send_message(req['telegram_id'], msg_to_user, reply_markup=main_menu(req['telegram_id']))
            except Exception:
                pass
        conn.close()

    elif data.startswith("rej_tmreq_"):
        req_id = int(data.replace("rej_tmreq_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id FROM team_change_requests WHERE id = %s", (req_id,))
        req = cursor.fetchone()

        if req:
            cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
            conn.commit()

            bot.edit_message_text("Team Change Rejected", call.message.chat.id, call.message.message_id)

            msg_to_user = "Your request to change your Team has been Failed"
            try:
                bot.send_message(req['telegram_id'], msg_to_user, reply_markup=main_menu(req['telegram_id']))
            except Exception:
                pass
        conn.close()

    elif data.startswith("view_mem_"):
        target_tg_id = int(data.replace("view_mem_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (target_tg_id,))
        m = cursor.fetchone()
        conn.close()

        if m:
            card = (
                f"👤Registration Information:\n\n"
                f"FB: {m['fb_name']}\n"
                f"Full Name: {m['full_name']}\n"
                f"ID: {m['unique_id']}\n"
                f"Team: {m['team_name']}\n"
                f"TG ID: {m['telegram_id']}\n"
                f"🫆Security Code: {m['security_code'] if m['security_code'] else ''}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Back", callback_data=f"back_mem_list_{m['team_name']}"))
            bot.edit_message_text(card, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("back_mem_list_"):
        team_name = data.replace("back_mem_list_", "")
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, full_name, unique_id, team_name, security_code FROM members WHERE team_name = %s AND is_blocked = FALSE AND is_removed = FALSE", (team_name,))
        members = cursor.fetchall()
        conn.close()

        markup = InlineKeyboardMarkup()
        for m in members:
            display_name = m['full_name'] or m['fb_name'] or str(m['telegram_id'])
            markup.add(InlineKeyboardButton(display_name, callback_data=f"view_mem_{m['telegram_id']}"))

        bot.edit_message_text(f"Members of {team_name}:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# 🚀 Polling Runner
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print("🤖 KBKh Registration Bot is Running...")

    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook Clean Note: {e}")

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"Polling conflict handled: {e}")
            time.sleep(5)
