import os
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# Flask Uptime Server
app = Flask('')

@app.route('/')
def home():
    return "KBKh Registration Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# Database Connection
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# Auto DB Tables Setup
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
                is_blocked BOOLEAN DEFAULT FALSE,
                is_removed BOOLEAN DEFAULT FALSE,
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

# Teams Mapping
INFO_TEAMS = ["Alpha", "Beta", "Gamma"]
MEME_TEAMS = ["Electron", "Proton", "Neutron"]
TEAMS = INFO_TEAMS + MEME_TEAMS

user_temp_data = {}

# Security Code Generator
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

# Status Checker
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

# Main Keyboards
def main_menu(user_id):
    status = get_user_status(user_id)
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

    if status == "ADMIN":
        markup.add(
            KeyboardButton("Pending Applications"),
            KeyboardButton("Members List")
        )
    elif status == "Approved":
        markup.add(
            KeyboardButton("My Profile"),
            KeyboardButton("Change Fb Name"),
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
            KeyboardButton("Already Registered?")
        )
    return markup

def step_inline_keyboard(step, has_back=True):
    markup = InlineKeyboardMarkup()
    buttons = []
    if has_back:
        buttons.append(InlineKeyboardButton("Back", callback_data=f"step_back_{step}"))
    buttons.append(InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt"))
    markup.row(*buttons)
    return markup

def team_select_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("Alpha", callback_data="select_team_Alpha"),
        InlineKeyboardButton("Beta", callback_data="select_team_Beta"),
        InlineKeyboardButton("Gamma", callback_data="select_team_Gamma")
    )
    markup.add(
        InlineKeyboardButton("Electron", callback_data="select_team_Electron"),
        InlineKeyboardButton("Proton", callback_data="select_team_Proton"),
        InlineKeyboardButton("Neutron", callback_data="select_team_Neutron")
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="step_back_team"),
        InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt")
    )
    return markup

# Start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return
    elif status == "ADMIN":
        text = "Admin Panel Active"
    elif status == "Approved":
        text = "Welcome to KBKh Science Ecosystem!"
    elif status == "Pending":
        text = "Status: Pending⏳"
    else:
        text = "Welcome! Press Register Now to start."

    bot.send_message(message.chat.id, text, reply_markup=main_menu(tg_id))

# Refresh Status Button
@bot.message_handler(func=lambda msg: msg.text in ["Refresh Status 🔄", "🔄 Check Status / Refresh", "Check Status / Refresh"])
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
        bot.send_message(message.chat.id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(tg_id))

# Registration Start
@bot.message_handler(func=lambda msg: msg.text in ["Register Now", "📝 Register Now"])
def reg_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return
    if status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
        return
    elif status == "Approved":
        bot.send_message(message.chat.id, "You are already registered!", reply_markup=main_menu(tg_id))
        return

    user_temp_data[tg_id] = {'step': 1}
    ask_fb_name(message.chat.id, tg_id)

def ask_fb_name(chat_id, tg_id, message_id=None):
    user_temp_data[tg_id]['step'] = 1
    text = "Enter Your Facebook Profile Name"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt"))

    if message_id:
        msg = bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        msg = bot.send_message(chat_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_fb_name_input)

def process_fb_name_input(message):
    tg_id = message.from_user.id
    if user_temp_data.get(tg_id, {}).get('step') != 1:
        return
    user_temp_data[tg_id]['fb_name'] = message.text.strip()
    ask_full_name(message.chat.id, tg_id)

def ask_full_name(chat_id, tg_id):
    user_temp_data[tg_id]['step'] = 2
    text = "Enter Your Full Name In English"
    msg = bot.send_message(chat_id, text, reply_markup=step_inline_keyboard(step=2, has_back=True))
    bot.register_next_step_handler(msg, process_full_name_input)

def process_full_name_input(message):
    tg_id = message.from_user.id
    if user_temp_data.get(tg_id, {}).get('step') != 2:
        return
    user_temp_data[tg_id]['full_name'] = message.text.strip()
    ask_unique_id(message.chat.id, tg_id)

def ask_unique_id(chat_id, tg_id, alert_prefix=""):
    user_temp_data[tg_id]['step'] = 3
    text = f"{alert_prefix}Enter Your Unique ID" if alert_prefix else "Enter Your Unique ID"
    msg = bot.send_message(chat_id, text, reply_markup=step_inline_keyboard(step=3, has_back=True))
    bot.register_next_step_handler(msg, process_unique_id_input)

def process_unique_id_input(message):
    tg_id = message.from_user.id
    if user_temp_data.get(tg_id, {}).get('step') != 3:
        return
    user_temp_data[tg_id]['unique_id'] = message.text.strip()
    ask_team_select(message.chat.id, tg_id)

def ask_team_select(chat_id, tg_id):
    user_temp_data[tg_id]['step'] = 4
    bot.clear_step_handler_by_chat_id(chat_id)
    text = "Select Your Team"
    bot.send_message(chat_id, text, reply_markup=team_select_keyboard())

# Summary Review Step
def show_summary_review(chat_id, tg_id):
    user_temp_data[tg_id]['step'] = 5
    data = user_temp_data.get(tg_id, {})
    text = (
        f"👤Your KBKh Profile Summary\n\n"
        f"FB Name: {data.get('fb_name', '')}\n"
        f"Full Name: {data.get('full_name', '')}\n"
        f"Unique ID: {data.get('unique_id', '')}\n"
        f"Team: {data.get('team_name', '')}\n\n"
        f"Please recheck your final profile"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Submit", callback_data="confirm_final_submit"),
        InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt")
    )
    bot.send_message(chat_id, text, reply_markup=markup)

# My Profile
@bot.message_handler(func=lambda msg: msg.text in ["My Profile", "👤 My Profile"])
def view_profile(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(tg_id))
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
            bot.send_message(message.chat.id, "Data not found!", reply_markup=main_menu(tg_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}", reply_markup=main_menu(tg_id))

# Change FB Name Flow
@bot.message_handler(func=lambda msg: msg.text in ["Change Fb Name", "🔄 Change FB Name"])
def change_fb_name_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(tg_id))
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Submit", callback_data="submit_fb_name_change"),
        InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt")
    )
    msg = bot.send_message(message.chat.id, "Enter your new Facebook Profile Name:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_fb_name_change_text)

def process_fb_name_change_text(message):
    tg_id = message.from_user.id
    user_temp_data[tg_id] = user_temp_data.get(tg_id, {})
    user_temp_data[tg_id]['new_fb_name'] = message.text.strip()

# Request Team Change Flow
@bot.message_handler(func=lambda msg: msg.text in ["Request Team Change", "🔄 Request Team Change"])
def team_change_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)

    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return

    if status != "Approved" and status != "ADMIN":
        bot.send_message(message.chat.id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(tg_id))
        return

    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("Alpha", callback_data="req_team_Alpha"),
        InlineKeyboardButton("Beta", callback_data="req_team_Beta"),
        InlineKeyboardButton("Gamma", callback_data="req_team_Gamma")
    )
    markup.add(
        InlineKeyboardButton("Electron", callback_data="req_team_Electron"),
        InlineKeyboardButton("Proton", callback_data="req_team_Proton"),
        InlineKeyboardButton("Neutron", callback_data="req_team_Neutron")
    )
    markup.add(
        InlineKeyboardButton("Cancel", callback_data="step_cancel_prompt")
    )
    bot.send_message(message.chat.id, "Select Team", reply_markup=markup)

# Callback Handlers
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    tg_id = call.from_user.id
    if get_user_status(tg_id) == "Blocked":
        bot.answer_callback_query(call.id, "Access Blocked⛔", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    data = call.data

    # Cancel Flow
    if data == "step_cancel_prompt":
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data="confirm_cancel_yes"),
            InlineKeyboardButton("No❌", callback_data="confirm_cancel_no")
        )
        bot.send_message(call.message.chat.id, "Are you sure you want to cancle the Process?", reply_markup=markup)

    elif data == "confirm_cancel_yes":
        user_temp_data.pop(tg_id, None)
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        bot.edit_message_text("Process Cancelled✅", call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Main Menu", reply_markup=main_menu(tg_id))

    elif data == "confirm_cancel_no":
        bot.edit_message_text("Process Resumed", call.message.chat.id, call.message.message_id)
        step = user_temp_data.get(tg_id, {}).get('step', 1)
        if step == 1:
            ask_fb_name(call.message.chat.id, tg_id)
        elif step == 2:
            ask_full_name(call.message.chat.id, tg_id)
        elif step == 3:
            ask_unique_id(call.message.chat.id, tg_id)
        elif step == 4:
            ask_team_select(call.message.chat.id, tg_id)

    # Back Navigation
    elif data.startswith("step_back_"):
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        curr_step = data.replace("step_back_", "")
        if curr_step in ["2", "team"]:
            ask_fb_name(call.message.chat.id, tg_id)
        elif curr_step == "3":
            ask_full_name(call.message.chat.id, tg_id)

    # Team Selection and Unique ID Logic Check
    elif data.startswith("select_team_"):
        selected_team = data.replace("select_team_", "")
        data_store = user_temp_data.get(tg_id, {})
        unique_id = data_store.get('unique_id', '').strip()

        cat_teams = INFO_TEAMS if selected_team in INFO_TEAMS else MEME_TEAMS

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM members WHERE LOWER(unique_id) = LOWER(%s) AND team_name = ANY(%s) AND is_removed = FALSE AND status != 'Removed'",
                (unique_id, cat_teams)
            )
            exists_count = cursor.fetchone()[0]
            conn.close()

            if exists_count > 0:
                ask_unique_id(call.message.chat.id, tg_id, alert_prefix="⚠️ Invalid Unique Id\n\n")
                return

            user_temp_data[tg_id]['team_name'] = selected_team
            show_summary_review(call.message.chat.id, tg_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    # Final Submit Registration
    elif data == "confirm_final_submit":
        data_store = user_temp_data.get(tg_id, {})
        fb_name = data_store.get('fb_name', '')
        full_name = data_store.get('full_name', '')
        unique_id = data_store.get('unique_id', '')
        team_name = data_store.get('team_name', '')

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE telegram_id = %s", (tg_id,))
            cursor.execute(
                "INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status) VALUES (%s, %s, %s, %s, %s, 'General Member', 'Pending')",
                (tg_id, fb_name, full_name, unique_id, team_name)
            )
            conn.commit()
            conn.close()

            bot.edit_message_text(
                "✅ Registration Request Submitted!\n\nYour application has been placed on admin pending!",
                call.message.chat.id,
                call.message.message_id
            )
            bot.send_message(call.message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))

            if ADMIN_CHAT_ID:
                admin_markup = InlineKeyboardMarkup()
                admin_markup.add(
                    InlineKeyboardButton("Approve", callback_data=f"app_user_{tg_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"rej_user_{tg_id}")
                )
                bot.send_message(
                    ADMIN_CHAT_ID,
                    f"New Registration:\nFB: {fb_name}\nFull Name: {full_name}\nID: {unique_id}\nTeam: {team_name}\nTG ID: {tg_id}",
                    reply_markup=admin_markup
                )
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    # Change FB Name Submit
    elif data == "submit_fb_name_change":
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        new_name = user_temp_data.get(tg_id, {}).get('new_fb_name')
        if not new_name:
            bot.send_message(call.message.chat.id, "Please enter your new FB name first.")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (tg_id,))
            user = cursor.fetchone()
            if user:
                old_name, team = user
                cursor.execute(
                    "INSERT INTO fb_name_requests (telegram_id, old_name, new_name, status) VALUES (%s, %s, %s, 'Pending') RETURNING id",
                    (tg_id, old_name, new_name)
                )
                req_id = cursor.fetchone()[0]
                conn.commit()
                conn.close()

                bot.edit_message_text(
                    "✅ FB Name Change Request Submitted!\n\nYour application has been placed on admin pending!",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.send_message(call.message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))

                if ADMIN_CHAT_ID:
                    admin_markup = InlineKeyboardMarkup()
                    admin_markup.add(
                        InlineKeyboardButton("Approve", callback_data=f"app_fbreq_{req_id}"),
                        InlineKeyboardButton("Reject", callback_data=f"rej_fbreq_{req_id}")
                    )
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"FB Name Change Request:\nOld: {old_name}\nNew: {new_name}\nTeam: {team}\nTG ID: {tg_id}",
                        reply_markup=admin_markup
                    )
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    # Request Team Change Submit
    elif data.startswith("req_team_"):
        new_team = data.replace("req_team_", "")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT team_name, fb_name FROM members WHERE telegram_id = %s", (tg_id,))
            user = cursor.fetchone()
            if user:
                old_team, fb_name = user
                cursor.execute(
                    "INSERT INTO team_change_requests (telegram_id, old_team, requested_team, status) VALUES (%s, %s, %s, 'Pending') RETURNING id",
                    (tg_id, old_team, new_team)
                )
                req_id = cursor.fetchone()[0]
                conn.commit()
                conn.close()

                bot.edit_message_text(
                    "✅ Team Change Request Submitted!\n\nYour application has been placed on admin pending!",
                    call.message.chat.id,
                    call.message.message_id
                )
                bot.send_message(call.message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))

                if ADMIN_CHAT_ID:
                    admin_markup = InlineKeyboardMarkup()
                    admin_markup.add(
                        InlineKeyboardButton("Approve", callback_data=f"app_tmreq_{req_id}"),
                        InlineKeyboardButton("Reject", callback_data=f"rej_tmreq_{req_id}")
                    )
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"Team Change Request:\nMember: {fb_name}\nOld Team: {old_team}\nNew Team: {new_team}\nTG ID: {tg_id}",
                        reply_markup=admin_markup
                    )
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    # Admin Approval Feedbacks
    elif data.startswith("app_user_"):
        target_id = int(data.replace("app_user_", ""))
        try:
            conn = get_db_connection()
            sec_code = generate_security_code(conn)
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s RETURNING full_name, team_name", (sec_code, target_id))
            res = cursor.fetchone()
            conn.commit()
            conn.close()

            if res:
                full_name, team = res[0], res[1]
                msg_text = (
                    f"Registration approval was successful!✅\n\n"
                    f"Welcome {full_name}!\n\n"
                    f"Team: {team}\n\n"
                    f"Your Security Code: {sec_code}\n\n"
                    f"⚠️Please do not share you security code with anyone."
                )
                bot.send_message(target_id, msg_text, reply_markup=main_menu(target_id))
                bot.edit_message_text("Approved Successfully!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    elif data.startswith("rej_user_"):
        target_id = int(data.replace("rej_user_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET status = 'Rejected' WHERE telegram_id = %s", (target_id,))
            conn.commit()
            conn.close()

            bot.send_message(target_id, "Registration Failed!\nPlease Try Again.", reply_markup=main_menu(target_id))
            bot.edit_message_text("Rejected Successfully!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    elif data.startswith("app_fbreq_"):
        req_id = int(data.replace("app_fbreq_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, new_name FROM fb_name_requests WHERE id = %s", (req_id,))
            req = cursor.fetchone()
            if req:
                u_id, new_name = req
                cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (new_name, u_id))
                cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s", (req_id,))
                conn.commit()
                conn.close()

                bot.send_message(u_id, f"Your request to change your FB Name has been approved✅\n\nNew FB Name: {new_name}", reply_markup=main_menu(u_id))
                bot.edit_message_text("Approved FB Name Change!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    elif data.startswith("rej_fbreq_"):
        req_id = int(data.replace("rej_fbreq_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id FROM fb_name_requests WHERE id = %s", (req_id,))
            req = cursor.fetchone()
            if req:
                u_id = req[0]
                cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
                conn.commit()
                conn.close()

                bot.send_message(u_id, "Your request to change your FB Name has been Failed", reply_markup=main_menu(u_id))
                bot.edit_message_text("Rejected FB Name Change!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    elif data.startswith("app_tmreq_"):
        req_id = int(data.replace("app_tmreq_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, requested_team FROM team_change_requests WHERE id = %s", (req_id,))
            req = cursor.fetchone()
            if req:
                u_id, new_team = req
                cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s", (new_team, u_id))
                cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s", (req_id,))
                conn.commit()
                conn.close()

                bot.send_message(u_id, f"Your request to change your Team has been approved✅\n\nNew Team: {new_team}", reply_markup=main_menu(u_id))
                bot.edit_message_text("Approved Team Change!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

    elif data.startswith("rej_tmreq_"):
        req_id = int(data.replace("rej_tmreq_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id FROM team_change_requests WHERE id = %s", (req_id,))
            req = cursor.fetchone()
            if req:
                u_id = req[0]
                cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s", (req_id,))
                conn.commit()
                conn.close()

                bot.send_message(u_id, "Your request to change your Team has been Failed", reply_markup=main_menu(u_id))
                bot.edit_message_text("Rejected Team Change!", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error: {e}")

# Run Bot and Flask Server
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    bot.infinity_polling(skip_pending=True)
