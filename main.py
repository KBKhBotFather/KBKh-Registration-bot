import os
import threading
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ⚙️ Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Server
app = Flask('')

@app.route('/')
def home():
    return "KBKh Registration Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# 🔌 Database Connection
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing in Render!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛠️ DB Setup
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
            ALTER TABLE members ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;
            ALTER TABLE members ADD COLUMN IF NOT EXISTS is_removed BOOLEAN DEFAULT FALSE;
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
            CREATE TABLE IF NOT EXISTS bots_list (
                id SERIAL PRIMARY KEY,
                team_category TEXT,
                username TEXT
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

INFO_TEAMS = ["Team Alpha", "Team Beta", "Team Gamma"]
MEME_TEAMS = ["Team Electron", "Team Proton", "Team Neutron"]
user_temp_data = {}

def get_admin_state(tg_id):
    if tg_id not in user_temp_data: user_temp_data[tg_id] = {}
    st = user_temp_data[tg_id]
    st.setdefault('exp_reg', set())
    st.setdefault('exp_fb', set())
    st.setdefault('exp_tc', set())
    st.setdefault('exp_mem', set())
    st.setdefault('proc_msgs', [])
    st.setdefault('ab_del', set())
    return st

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

def get_preview_code(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM members WHERE security_code IS NOT NULL")
        cnt = cursor.fetchone()[0] + 1
        return f"KBKh2022{cnt}"
    except Exception:
        return "KBKh2022***"

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
            if res[2] or res[0] == "Removed": return "UNREGISTERED"
            if res[1] or res[0] == "Blocked": return "Blocked"
            return res[0]
        return "UNREGISTERED"
    except Exception:
        return "UNREGISTERED"

# 📱 Reply Keyboards (Persistent Fix Applied Here)
def create_reply_kb(row_width=2):
    try:
        return ReplyKeyboardMarkup(row_width=row_width, resize_keyboard=True, is_persistent=True)
    except TypeError:
        return ReplyKeyboardMarkup(row_width=row_width, resize_keyboard=True)

def main_menu(user_id):
    status = get_user_status(user_id)
    markup = create_reply_kb(row_width=2)
    if status == "ADMIN":
        markup.add(KeyboardButton("Pending Applications"), KeyboardButton("Members List"))
        markup.add(KeyboardButton("Add Bot"))
    elif status == "Approved":
        markup.add(KeyboardButton("My Profile"), KeyboardButton("Change FB Name"))
        markup.add(KeyboardButton("Request Team Change"), KeyboardButton("My Bots"))
    elif status == "Pending":
        markup.add(KeyboardButton("🔄 Refresh Status"))
    elif status == "Blocked":
        return None
    else:
        markup.add(KeyboardButton("Registration Now"), KeyboardButton("Already Registered"))
    return markup

def cancel_only_kb():
    return create_reply_kb().add(KeyboardButton("Cancel"))

def back_cancel_kb():
    markup = create_reply_kb(row_width=2)
    markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))
    return markup

def submit_cancel_kb():
    markup = create_reply_kb(row_width=2)
    markup.add(KeyboardButton("Submit"), KeyboardButton("Cancel"))
    return markup

def cancel_process(message):
    tg_id = message.from_user.id
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_temp_data.pop(tg_id, None)
    bot.send_message(message.chat.id, "Process Cancelled✅", reply_markup=main_menu(tg_id))

def enforce_registration(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status == "UNREGISTERED":
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.send_message(message.chat.id, "You are not registered!\nPlease complete the registration...", reply_markup=main_menu(tg_id))
        return True
    if status == "Blocked":
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.send_message(message.chat.id, "Access Blocked⛔", reply_markup=ReplyKeyboardRemove())
        return True
    return False

# 📌 Core Commands
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status == "UNREGISTERED":
        bot.send_message(message.chat.id, "Welcome to KBKh Science Ecosystem!", reply_markup=main_menu(tg_id))
    elif status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔", reply_markup=ReplyKeyboardRemove())
    else:
        bot.send_message(message.chat.id, "Welcome to KBKh Science Ecosystem!", reply_markup=main_menu(tg_id))

@bot.message_handler(func=lambda msg: msg.text == "🔄 Refresh Status")
def check_status_refresh(message):
    if enforce_registration(message): return
    status = get_user_status(message.from_user.id)
    if status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(message.from_user.id))
    elif status == "Approved":
        bot.send_message(message.chat.id, "Registration approval was successful!✅", reply_markup=main_menu(message.from_user.id))

# 📝 1. NEW REGISTRATION FLOW (Inline Team Select & Confirm)
@bot.message_handler(func=lambda msg: msg.text == "Registration Now")
def reg_start(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "UNREGISTERED":
        return bot.send_message(message.chat.id, "Action not allowed.", reply_markup=main_menu(tg_id))
    user_temp_data[tg_id] = {}
    msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_only_kb())
    bot.register_next_step_handler(msg, step_fb_name)

def step_fb_name(message):
    if message.text == "Cancel": return cancel_process(message)
    tg_id = message.from_user.id
    user_temp_data[tg_id]['fb'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=back_cancel_kb())
    bot.register_next_step_handler(msg, step_full_name)

def step_full_name(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Back":
        msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_only_kb())
        bot.register_next_step_handler(msg, step_fb_name)
        return
    user_temp_data[tg_id]['full'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Enter Your Unique ID (Given by Team)", reply_markup=back_cancel_kb())
    bot.register_next_step_handler(msg, step_uid)

def step_uid(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Back":
        msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=back_cancel_kb())
        bot.register_next_step_handler(msg, step_full_name)
        return
    user_temp_data[tg_id]['uid'] = message.text.strip()
    
    # Hide Text Input bar cleanly
    rm_msg = bot.send_message(message.chat.id, "⏳", reply_markup=ReplyKeyboardRemove())
    bot.delete_message(message.chat.id, rm_msg.message_id)

    # Move to Inline Keyboard for team selection (No typing possible!)
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("Alpha", callback_data="reg_t_Alpha"),
           InlineKeyboardButton("Beta", callback_data="reg_t_Beta"),
           InlineKeyboardButton("Gamma", callback_data="reg_t_Gamma"))
    kb.add(InlineKeyboardButton("Electron", callback_data="reg_t_Electron"),
           InlineKeyboardButton("Proton", callback_data="reg_t_Proton"),
           InlineKeyboardButton("Neutron", callback_data="reg_t_Neutron"))
    kb.row(InlineKeyboardButton("Back", callback_data="reg_back_team"), InlineKeyboardButton("Cancel", callback_data="reg_cancel"))

    bot.send_message(message.chat.id, "Select Your Team", reply_markup=kb)


# 🔑 2. ALREADY REGISTERED
@bot.message_handler(func=lambda msg: msg.text == "Already Registered")
def recovery_start(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "UNREGISTERED": return
    msg = bot.send_message(message.chat.id, "Enter your security code to restore your account.", reply_markup=cancel_only_kb())
    bot.register_next_step_handler(msg, process_recovery)

def process_recovery(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    sec_code = message.text.strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id FROM members WHERE security_code = %s AND is_blocked = FALSE AND is_removed = FALSE", (sec_code,))
        user = cursor.fetchone()
        if user:
            old_tg = user['telegram_id']
            cursor.execute("DELETE FROM fb_name_requests WHERE telegram_id = %s", (tg_id,))
            cursor.execute("DELETE FROM team_change_requests WHERE telegram_id = %s", (tg_id,))
            cursor.execute("DELETE FROM members WHERE telegram_id = %s", (tg_id,))
            cursor.execute("UPDATE members SET telegram_id = %s WHERE security_code = %s", (tg_id, sec_code))
            cursor.execute("UPDATE fb_name_requests SET telegram_id = %s WHERE telegram_id = %s", (tg_id, old_tg))
            cursor.execute("UPDATE team_change_requests SET telegram_id = %s WHERE telegram_id = %s", (tg_id, old_tg))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, "Your account has been successfully recovered!✅", reply_markup=main_menu(tg_id))
        else:
            conn.close()
            msg = bot.send_message(message.chat.id, "Failed❌ Invalid Code. Enter your security code to restore your account.", reply_markup=cancel_only_kb())
            bot.register_next_step_handler(msg, process_recovery)
    except Exception:
        bot.send_message(message.chat.id, "Process Failed❌", reply_markup=main_menu(tg_id))


# 👤 3. MY PROFILE
@bot.message_handler(func=lambda msg: msg.text == "My Profile")
def view_profile(message):
    if enforce_registration(message): return
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, security_code FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            team_disp = str(user[3]).replace("Team ", "")
            profile_msg = (f"👤Your KBKh Profile Summary\n"
                           f"FB Name: {user[0]}\n"
                           f"Full Name: {user[1]}\n"
                           f"Unique ID: {user[2]}\n"
                           f"Team: {team_disp}\n"
                           f"🫆Security Code: {user[4]}")
            bot.send_message(message.chat.id, profile_msg, reply_markup=main_menu(tg_id))
    except Exception: pass


# 🔄 4. CHANGE FB NAME
@bot.message_handler(func=lambda msg: msg.text == "Change FB Name")
def change_fb_start(message):
    if enforce_registration(message): return
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM fb_name_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        if cursor.fetchone():
            conn.close()
            return bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
        conn.close()
    except Exception: pass
    msg = bot.send_message(message.chat.id, "Enter your new Facebook Profile Name:", reply_markup=cancel_only_kb())
    bot.register_next_step_handler(msg, process_fb_change)

def process_fb_change(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    user_temp_data[tg_id] = {'new_fb': message.text.strip()}
    msg = bot.send_message(message.chat.id, f"New FB Name: {message.text.strip()}\n\nClick submit to confirm", reply_markup=submit_cancel_kb())
    bot.register_next_step_handler(msg, process_fb_submit)

def process_fb_submit(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Submit":
        new_fb = user_temp_data.get(tg_id, {}).get('new_fb', '')
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT fb_name, team_name FROM members WHERE telegram_id = %s", (tg_id,))
            res = cursor.fetchone()
            old_fb, team = res[0], str(res[1]).replace("Team ", "")
            cursor.execute("INSERT INTO fb_name_requests (telegram_id, old_name, new_name, status) VALUES (%s, %s, %s, 'Pending') RETURNING id", (tg_id, old_fb, new_fb))
            req_id = cursor.fetchone()[0]
            conn.commit()
            
            if ADMIN_CHAT_ID:
                admin_text = (f"Old FB: {old_fb}\n"
                              f"New FB: {new_fb}\n"
                              f"Team: {team}")
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("Approve", callback_data=f"dm_apf_{req_id}"), InlineKeyboardButton("Reject", callback_data=f"dm_rjf_{req_id}"))
                bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=kb)
            conn.close()
            bot.send_message(message.chat.id, "✅ FB Name Change Request Submitted!\n\nYour application has been placed on admin pending!", reply_markup=main_menu(tg_id))
        except Exception:
            bot.send_message(message.chat.id, "Failed❌", reply_markup=main_menu(tg_id))


# 🔄 5. REQUEST TEAM CHANGE
def get_tc_inline_kb(current_full, selected_short=None):
    kb = InlineKeyboardMarkup(row_width=3)
    teams = ["Alpha", "Beta", "Gamma", "Electron", "Proton", "Neutron"]
    buttons = []
    for t in teams:
        text = t
        if selected_short == t:
            if f"Team {t}" == current_full: text = f"🔴 {t}"
            else: text = f"✅ {t}"
        buttons.append(InlineKeyboardButton(text, callback_data=f"tc_sel_{t}"))
    kb.add(*buttons[:3])
    kb.add(*buttons[3:])
    kb.row(InlineKeyboardButton("Submit", callback_data="tc_submit"), InlineKeyboardButton("Cancel", callback_data="tc_cancel"))
    return kb

@bot.message_handler(func=lambda msg: msg.text == "Request Team Change")
def tc_start(message):
    if enforce_registration(message): return
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM team_change_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        if cursor.fetchone():
            conn.close()
            return bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
        cursor.execute("SELECT team_name, fb_name FROM members WHERE telegram_id = %s", (tg_id,))
        res = cursor.fetchone()
        conn.close()
        
        user_temp_data[tg_id] = {'current_team': res[0], 'fb_name': res[1], 'selected_tc': None}
        bot.send_message(message.chat.id, "Select Team", reply_markup=get_tc_inline_kb(res[0]))
    except Exception: pass


# 🤖 6. MY BOTS (General User Feature)
@bot.message_handler(func=lambda msg: msg.text == "My Bots")
def user_my_bots(message):
    if enforce_registration(message): return
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT team_name FROM members WHERE telegram_id = %s", (tg_id,))
        res = cursor.fetchone()
        if not res:
            conn.close()
            return
        
        cat_str = "Info Team" if res[0] in INFO_TEAMS else "Meme Team"
        
        cursor.execute("SELECT username FROM bots_list WHERE team_category = %s", (cat_str,))
        bots = cursor.fetchall()
        conn.close()
        
        if not bots:
            text = "You can use all these bots:\n\n(coming soon!)"
        else:
            bot_names = "\n\n".join([b[0] for b in bots])
            text = f"You can use all these bots:\n\n{bot_names}"
            
        bot.send_message(message.chat.id, text, reply_markup=main_menu(tg_id))
    except Exception:
        pass


# 👑 7. ADMIN PANEL
@bot.message_handler(func=lambda msg: msg.text == "Pending Applications")
def admin_pend(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID: return
    render_admin_pend_menu(message.chat.id)

def render_admin_pend_menu(chat_id, message_id=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'Pending' AND is_blocked = FALSE AND is_removed = FALSE")
        c1 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM fb_name_requests fr JOIN members m ON fr.telegram_id = m.telegram_id WHERE fr.status = 'Pending' AND m.is_blocked = FALSE AND m.is_removed = FALSE")
        c2 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM team_change_requests tc JOIN members m ON tc.telegram_id = m.telegram_id WHERE tc.status = 'Pending' AND m.is_blocked = FALSE AND m.is_removed = FALSE")
        c3 = cursor.fetchone()[0]
        conn.close()
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(f"🎫Registration Application - {c1}", callback_data="in_ad_p_reg"),
               InlineKeyboardButton(f"🎟️Fb Name Change Application - {c2}", callback_data="in_ad_p_fb"),
               InlineKeyboardButton(f"Team Change Application - {c3}", callback_data="in_ad_p_tc"),
               InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
        text = "Pending Applications:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
        else: bot.send_message(chat_id, text, reply_markup=kb)
    except Exception: pass

@bot.message_handler(func=lambda msg: msg.text == "Members List")
def admin_mem_list(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID: return
    render_admin_mem_menu(message.chat.id)

def render_admin_mem_menu(chat_id, message_id=None):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("Alpha", callback_data="in_ad_t_Alpha"), InlineKeyboardButton("Beta", callback_data="in_ad_t_Beta"), InlineKeyboardButton("Gamma", callback_data="in_ad_t_Gamma"))
    kb.add(InlineKeyboardButton("Electron", callback_data="in_ad_t_Electron"), InlineKeyboardButton("Proton", callback_data="in_ad_t_Proton"), InlineKeyboardButton("Neutron", callback_data="in_ad_t_Neutron"))
    kb.add(InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    if message_id: bot.edit_message_text("Select Team", chat_id, message_id, reply_markup=kb)
    else: bot.send_message(chat_id, "Select Team", reply_markup=kb)

# --- ADD BOT ADMIN PANEL ---
@bot.message_handler(func=lambda msg: msg.text == "Add Bot")
def admin_add_bot(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID: return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(InlineKeyboardButton("Info Team", callback_data="ab_cat_Info"), InlineKeyboardButton("Meme Team", callback_data="ab_cat_Meme"))
    kb.add(InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    bot.send_message(message.chat.id, "Select team to manage bots:", reply_markup=kb)

def render_ab_list(chat_id, message_id, tg_id):
    st = get_admin_state(tg_id)
    cat = st.get('ab_cat', 'Info')
    del_set = st.get('ab_del', set())
    team_str = "Info Team" if cat == "Info" else "Meme Team"
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM bots_list WHERE team_category = %s", (team_str,))
    bots = cursor.fetchall()
    conn.close()

    kb = InlineKeyboardMarkup(row_width=1)
    if not bots:
        kb.add(InlineKeyboardButton("(No bots added yet)", callback_data="ignore"))
    else:
        for b in bots:
            icon = "🗑️" if b['id'] in del_set else "❌"
            kb.add(InlineKeyboardButton(f"{b['username']} {icon}", callback_data=f"ab_tog_{b['id']}"))
            
    kb.row(InlineKeyboardButton("Add", callback_data="ab_add"), InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    kb.add(InlineKeyboardButton("Submit", callback_data="ab_submit"))
    
    bot.edit_message_text(f"Manage Bots ({team_str}):", chat_id, message_id, reply_markup=kb)

def process_add_bot(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    username = message.text.strip()
    if not username.startswith("@"): username = "@" + username
    
    st = get_admin_state(tg_id)
    cat = st.get('ab_cat', 'Info')
    team_str = "Info Team" if cat == "Info" else "Meme Team"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO bots_list (team_category, username) VALUES (%s, %s)", (team_str, username))
        conn.commit()
        conn.close()
        
        # Give Yes/No option natively through Inline Keyboard for neatness
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("Yes✅", callback_data="ab_more_yes"), InlineKeyboardButton("No❌", callback_data="ab_more_no"))
        
        rm_msg = bot.send_message(message.chat.id, "⏳", reply_markup=ReplyKeyboardRemove())
        bot.delete_message(message.chat.id, rm_msg.message_id)
        bot.send_message(message.chat.id, "Do you want to add more?", reply_markup=kb)
    except Exception:
        bot.send_message(message.chat.id, "Failed❌", reply_markup=main_menu(tg_id))

# --- LIST RENDERERS FOR ADMIN ---
def render_pend_reg_list(chat_id, message_id, tg_id):
    st = get_admin_state(tg_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM members WHERE status = 'Pending' AND is_blocked = FALSE AND is_removed = FALSE")
    reqs = cursor.fetchall()
    
    text_parts = []
    if st['proc_msgs']: text_parts.extend(st['proc_msgs'])
    
    kb = InlineKeyboardMarkup(row_width=1)
    if not reqs:
        text_parts.append("No Registration Applications found.")
    else:
        for r in reqs:
            if r['telegram_id'] in st['exp_reg']:
                t_disp = str(r['team_name']).replace("Team ", "")
                prof = (f"👤Profile Summary\n"
                        f"FB Name: {r['fb_name']}\n"
                        f"Full Name: {r['full_name']}\n"
                        f"Unique ID: {r['unique_id']}\n"
                        f"Team: {t_disp}\n"
                        f"🫆Security Code: {get_preview_code(conn)}\n\n")
                text_parts.append(prof)
                kb.add(InlineKeyboardButton(f"{r['fb_name']} 🔻", callback_data=f"preg_col_{r['telegram_id']}"))
                kb.row(InlineKeyboardButton("Approve", callback_data=f"lst_apr_{r['telegram_id']}"), InlineKeyboardButton("Reject", callback_data=f"lst_rjr_{r['telegram_id']}"))
            else:
                kb.add(InlineKeyboardButton(f"{r['fb_name']} 🔺", callback_data=f"preg_exp_{r['telegram_id']}"))
    
    conn.close()
    kb.row(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    final_text = "".join(text_parts).strip() if text_parts else "Empty"
    bot.edit_message_text(final_text, chat_id, message_id, reply_markup=kb)

def render_pend_fb_list(chat_id, message_id, tg_id):
    st = get_admin_state(tg_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT fr.*, m.team_name FROM fb_name_requests fr JOIN members m ON fr.telegram_id = m.telegram_id WHERE fr.status = 'Pending' AND m.is_blocked = FALSE AND m.is_removed = FALSE")
    reqs = cursor.fetchall()
    
    text_parts = []
    if st['proc_msgs']: text_parts.extend(st['proc_msgs'])
    kb = InlineKeyboardMarkup(row_width=1)
    
    if not reqs:
        text_parts.append("No FB Name Change Applications found.")
    else:
        for r in reqs:
            if r['id'] in st['exp_fb']:
                t_disp = str(r['team_name']).replace("Team ", "")
                prof = (f"Old FB: {r['old_name']}\n"
                        f"New FB: {r['new_name']}\n"
                        f"Team: {t_disp}\n\n")
                text_parts.append(prof)
                kb.add(InlineKeyboardButton(f"{r['old_name']} 🔻", callback_data=f"pfb_col_{r['id']}"))
                kb.row(InlineKeyboardButton("Approve", callback_data=f"lst_apf_{r['id']}"), InlineKeyboardButton("Reject", callback_data=f"lst_rjf_{r['id']}"))
            else:
                kb.add(InlineKeyboardButton(f"{r['old_name']} 🔺", callback_data=f"pfb_exp_{r['id']}"))
    
    conn.close()
    kb.row(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    final_text = "".join(text_parts).strip() if text_parts else "Empty"
    bot.edit_message_text(final_text, chat_id, message_id, reply_markup=kb)

def render_pend_tc_list(chat_id, message_id, tg_id):
    st = get_admin_state(tg_id)
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT tc.*, m.fb_name FROM team_change_requests tc JOIN members m ON tc.telegram_id = m.telegram_id WHERE tc.status = 'Pending' AND m.is_blocked = FALSE AND m.is_removed = FALSE")
    reqs = cursor.fetchall()
    
    text_parts = []
    if st['proc_msgs']: text_parts.extend(st['proc_msgs'])
    kb = InlineKeyboardMarkup(row_width=1)
    
    if not reqs:
        text_parts.append("No Team Change Applications found.")
    else:
        for r in reqs:
            if r['id'] in st['exp_tc']:
                o_disp = str(r['old_team']).replace("Team ", "")
                n_disp = str(r['requested_team']).replace("Team ", "")
                prof = (f"FB Name: {r['fb_name']}\n"
                        f"{o_disp} ➡️ {n_disp}\n\n")
                text_parts.append(prof)
                kb.add(InlineKeyboardButton(f"{r['fb_name']} 🔻", callback_data=f"ptc_col_{r['id']}"))
                kb.row(InlineKeyboardButton("Approve", callback_data=f"lst_apt_{r['id']}"), InlineKeyboardButton("Reject", callback_data=f"lst_rjt_{r['id']}"))
            else:
                kb.add(InlineKeyboardButton(f"{r['fb_name']} 🔺", callback_data=f"ptc_exp_{r['id']}"))
    
    conn.close()
    kb.row(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
    final_text = "".join(text_parts).strip() if text_parts else "Empty"
    bot.edit_message_text(final_text, chat_id, message_id, reply_markup=kb)


# 🔘 INLINE CALLBACKS
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    tg_id = call.from_user.id
    data = call.data
    st = get_admin_state(tg_id)
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    
    # 📝 INLINE REGISTRATION SELECTION LOGIC 
    if data.startswith("reg_t_"):
        team = data.split("_")[2]
        team_full = f"Team {team}"
        uid = user_temp_data[tg_id].get('uid')
        cat_teams = INFO_TEAMS if team_full in INFO_TEAMS else MEME_TEAMS
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM members WHERE LOWER(unique_id) = LOWER(%s) AND team_name = ANY(%s) AND is_removed = FALSE AND status != 'Removed'", (uid, cat_teams))
            exists_count = cursor.fetchone()[0]
            conn.close()
            
            if exists_count > 0:
                kb = InlineKeyboardMarkup(row_width=2)
                kb.row(InlineKeyboardButton("Back", callback_data="reg_back_team"), InlineKeyboardButton("Cancel", callback_data="reg_cancel"))
                bot.edit_message_text("⚠️ Invalid Unique Id\n\nSelect your team again or go back:", call.message.chat.id, call.message.message_id, reply_markup=kb)
                return
                
            user_temp_data[tg_id]['team_full'] = team_full
            user_temp_data[tg_id]['team_short'] = team
            summary = (f"👤Profile Summary\n"
                       f"FB Name: {user_temp_data[tg_id]['fb']}\n"
                       f"Full Name: {user_temp_data[tg_id]['full']}\n"
                       f"Unique ID: {uid}\n"
                       f"Team: {team}\n\n"
                       f"Please recheck your final profile")
            
            kb = InlineKeyboardMarkup(row_width=2)
            kb.row(InlineKeyboardButton("Submit", callback_data="reg_submit"), InlineKeyboardButton("Cancel", callback_data="reg_cancel"))
            bot.edit_message_text(summary, call.message.chat.id, call.message.message_id, reply_markup=kb)
        except Exception:
            bot.edit_message_text("Error processing request.", call.message.chat.id, call.message.message_id)

    elif data == "reg_back_team":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg = bot.send_message(call.message.chat.id, "Enter Your Unique ID (Given by Team)", reply_markup=back_cancel_kb())
        bot.register_next_step_handler(msg, step_uid)
        
    elif data == "reg_cancel":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        user_temp_data.pop(tg_id, None)
        bot.send_message(call.message.chat.id, "Process Cancelled✅", reply_markup=main_menu(tg_id))
        
    elif data == "reg_submit":
        db_data = user_temp_data.get(tg_id, {})
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE telegram_id = %s", (tg_id,))
            cursor.execute("INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", 
                           (tg_id, db_data.get('fb'), db_data.get('full'), db_data.get('uid'), db_data.get('team_full'), 'General Member'))
            conn.commit()
            
            if ADMIN_CHAT_ID:
                prev_code = get_preview_code(conn)
                admin_text = (f"🎫New Registration Request!\n\n"
                              f"👤Profile Summary\n"
                              f"FB Name: {db_data.get('fb')}\n"
                              f"Full Name: {db_data.get('full')}\n"
                              f"Unique ID: {db_data.get('uid')}\n"
                              f"Team: {db_data.get('team_short')}\n"
                              f"🫆Security Code: {prev_code}")
                kb = InlineKeyboardMarkup(row_width=2)
                kb.row(InlineKeyboardButton("Approve", callback_data=f"dm_apr_{tg_id}"), InlineKeyboardButton("Reject", callback_data=f"dm_rjr_{tg_id}"))
                bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=kb)
            conn.close()
            
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "✅ Registration Request Submitted!\n\nYour application has been placed on admin pending!", reply_markup=main_menu(tg_id))
            user_temp_data.pop(tg_id, None)
        except Exception:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "Submission Failed❌", reply_markup=main_menu(tg_id))

    # User Team Change Client Logic
    elif data.startswith("tc_sel_"):
        t = data.split("_")[2]
        curr = user_temp_data.get(tg_id, {}).get('current_team')
        user_temp_data[tg_id]['selected_tc'] = t
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_tc_inline_kb(curr, t))
    
    elif data == "tc_cancel":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif data == "tc_submit":
        sel = user_temp_data.get(tg_id, {}).get('selected_tc')
        curr = user_temp_data.get(tg_id, {}).get('current_team')
        fb = user_temp_data.get(tg_id, {}).get('fb_name')
        if not sel or f"Team {sel}" == curr: return
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO team_change_requests (telegram_id, old_team, requested_team, status) VALUES (%s, %s, %s, 'Pending') RETURNING id", (tg_id, curr, f"Team {sel}"))
            req_id = cursor.fetchone()[0]
            conn.commit()
            if ADMIN_CHAT_ID:
                admin_text = (f"FB Name: {fb}\n"
                              f"{str(curr).replace('Team ','')} ➡️ {sel}")
                kb = InlineKeyboardMarkup()
                kb.row(InlineKeyboardButton("Approve", callback_data=f"dm_apt_{req_id}"), InlineKeyboardButton("Reject", callback_data=f"dm_rjt_{req_id}"))
                bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=kb)
            conn.close()
            bot.edit_message_text("✅ Team Change Request Submitted!\n\nYour application has been placed on admin pending!", call.message.chat.id, call.message.message_id)
        except Exception: pass

    # --- ADMIN ADD BOT LOGIC ---
    elif data.startswith("ab_cat_"):
        cat = data.split("_")[2]
        st['ab_cat'] = cat
        st['ab_del'] = set()
        render_ab_list(call.message.chat.id, call.message.message_id, tg_id)
        
    elif data.startswith("ab_tog_"):
        bid = int(data.split("_")[2])
        if bid in st['ab_del']: st['ab_del'].remove(bid)
        else: st['ab_del'].add(bid)
        render_ab_list(call.message.chat.id, call.message.message_id, tg_id)
        
    elif data == "ab_submit":
        if not st['ab_del']: return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bots_list WHERE id = ANY(%s)", (list(st['ab_del']),))
        conn.commit()
        conn.close()
        st['ab_del'].clear()
        render_ab_list(call.message.chat.id, call.message.message_id, tg_id)
        
    elif data == "ab_add":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg = bot.send_message(call.message.chat.id, "Please enter a username:", reply_markup=cancel_only_kb())
        bot.register_next_step_handler(msg, process_add_bot)
        
    elif data == "ab_more_yes":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg = bot.send_message(call.message.chat.id, "Please enter a username:", reply_markup=cancel_only_kb())
        bot.register_next_step_handler(msg, process_add_bot)
        
    elif data == "ab_more_no":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Username added successfully✅", reply_markup=main_menu(tg_id))

    # --- DIRECT MESSAGE ACTIONS (From Admin DM) ---
    elif data.startswith("dm_apr_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        code = generate_security_code(conn)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s RETURNING full_name, team_name", (code, uid))
        user = cursor.fetchone()
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"Registration Approved✅\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
        if user:
            t_disp = str(user['team_name']).replace("Team ", "")
            msg = f"Registration approval was successful!✅\n\nWelcome {user['full_name']}!\n\nTeam: {t_disp}\n\nYour Security Code: {code}\n\n⚠️Please do not share you security code with anyone."
            try: bot.send_message(uid, msg)
            except: pass
            
    elif data.startswith("dm_rjr_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE telegram_id = %s", (uid,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"Registration Rejected❌\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, "Registration Failed❌\nPlease Try Again.")
        except: pass

    elif data.startswith("dm_apf_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, new_name", (req_id,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (req['new_name'], req['telegram_id']))
            conn.commit()
            bot.edit_message_text(f"Fb Name Change Approved✅\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
            try: bot.send_message(req['telegram_id'], f"Your request to change your FB Name has been approved✅\n\nNew FB Name: {req['new_name']}")
            except: pass
        conn.close()
        
    elif data.startswith("dm_rjf_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id", (req_id,))
        req = cursor.fetchone()
        conn.commit()
        conn.close()
        bot.edit_message_text(f"Fb Name Change Rejected❌\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
        if req:
            try: bot.send_message(req['telegram_id'], "Your request to change your FB Name has been Failed❌")
            except: pass

    elif data.startswith("dm_apt_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, requested_team", (req_id,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s", (req['requested_team'], req['telegram_id']))
            conn.commit()
            t_disp = str(req['requested_team']).replace("Team ", "")
            bot.edit_message_text(f"Team Change Approved✅\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
            try: bot.send_message(req['telegram_id'], f"Your request to change your Team has been approved✅\n\nNew Team: {t_disp}")
            except: pass
        conn.close()
        
    elif data.startswith("dm_rjt_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id", (req_id,))
        req = cursor.fetchone()
        conn.commit()
        conn.close()
        bot.edit_message_text(f"Team Change Rejected❌\n\n{call.message.text}", call.message.chat.id, call.message.message_id)
        if req:
            try: bot.send_message(req['telegram_id'], "Your request to change your Team has been Failed❌")
            except: pass

    # --- ADMIN INLINE NAVIGATION (Single Page) ---
    elif data == "ad_cancel_msg":
        st['proc_msgs'].clear()
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif data == "ad_back_pend":
        st['proc_msgs'].clear()
        st['exp_reg'].clear()
        st['exp_fb'].clear()
        st['exp_tc'].clear()
        render_admin_pend_menu(call.message.chat.id, call.message.message_id)
        
    elif data == "ad_back_mem":
        st['exp_mem'].clear()
        render_admin_mem_menu(call.message.chat.id, call.message.message_id)

    # Expanding/Collapsing Lists
    elif data == "in_ad_p_reg":
        st['proc_msgs'].clear()
        render_pend_reg_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("preg_exp_"):
        uid = int(data.split("_")[2])
        if len(st['exp_reg']) >= 3: st['exp_reg'].pop() 
        st['exp_reg'].add(uid)
        render_pend_reg_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("preg_col_"):
        uid = int(data.split("_")[2])
        st['exp_reg'].discard(uid)
        render_pend_reg_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data == "in_ad_p_fb":
        st['proc_msgs'].clear()
        render_pend_fb_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("pfb_exp_"):
        rid = int(data.split("_")[2])
        if len(st['exp_fb']) >= 3: st['exp_fb'].pop()
        st['exp_fb'].add(rid)
        render_pend_fb_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("pfb_col_"):
        rid = int(data.split("_")[2])
        st['exp_fb'].discard(rid)
        render_pend_fb_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data == "in_ad_p_tc":
        st['proc_msgs'].clear()
        render_pend_tc_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("ptc_exp_"):
        rid = int(data.split("_")[2])
        if len(st['exp_tc']) >= 3: st['exp_tc'].pop()
        st['exp_tc'].add(rid)
        render_pend_tc_list(call.message.chat.id, call.message.message_id, tg_id)
    elif data.startswith("ptc_col_"):
        rid = int(data.split("_")[2])
        st['exp_tc'].discard(rid)
        render_pend_tc_list(call.message.chat.id, call.message.message_id, tg_id)

    # List Actions
    elif data.startswith("lst_apr_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        code = generate_security_code(conn)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s RETURNING fb_name, full_name, team_name", (code, uid))
        user = cursor.fetchone()
        conn.commit()
        conn.close()
        
        st['exp_reg'].discard(uid)
        if user:
            st['proc_msgs'].append(f"{user['fb_name']} - Registration Approved✅\n\n")
            t_disp = str(user['team_name']).replace("Team ", "")
            msg = f"Registration approval was successful!✅\n\nWelcome {user['full_name']}!\n\nTeam: {t_disp}\n\nYour Security Code: {code}\n\n⚠️Please do not share you security code with anyone."
            try: bot.send_message(uid, msg)
            except: pass
        render_pend_reg_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data.startswith("lst_rjr_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("DELETE FROM members WHERE telegram_id = %s RETURNING fb_name", (uid,))
        user = cursor.fetchone()
        conn.commit()
        conn.close()
        
        st['exp_reg'].discard(uid)
        if user: st['proc_msgs'].append(f"{user['fb_name']} - Application Rejected❌\n\n")
        try: bot.send_message(uid, "Registration Failed❌\nPlease Try Again.")
        except: pass
        render_pend_reg_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data.startswith("lst_apf_"):
        rid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, new_name, old_name", (rid,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (req['new_name'], req['telegram_id']))
            conn.commit()
            st['exp_fb'].discard(rid)
            st['proc_msgs'].append(f"{req['old_name']} - FB Name Change Approved✅\n\n")
            try: bot.send_message(req['telegram_id'], f"Your request to change your FB Name has been approved✅\n\nNew FB Name: {req['new_name']}")
            except: pass
        conn.close()
        render_pend_fb_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data.startswith("lst_rjf_"):
        rid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id, old_name", (rid,))
        req = cursor.fetchone()
        conn.commit()
        if req:
            st['exp_fb'].discard(rid)
            st['proc_msgs'].append(f"{req['old_name']} - Application Rejected❌\n\n")
            try: bot.send_message(req['telegram_id'], "Your request to change your FB Name has been Failed❌")
            except: pass
        conn.close()
        render_pend_fb_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data.startswith("lst_apt_"):
        rid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, requested_team", (rid,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s RETURNING fb_name", (req['requested_team'], req['telegram_id']))
            mem = cursor.fetchone()
            conn.commit()
            st['exp_tc'].discard(rid)
            if mem: st['proc_msgs'].append(f"{mem['fb_name']} - Team Change Approved✅\n\n")
            t_disp = str(req['requested_team']).replace("Team ", "")
            try: bot.send_message(req['telegram_id'], f"Your request to change your Team has been approved✅\n\nNew Team: {t_disp}")
            except: pass
        conn.close()
        render_pend_tc_list(call.message.chat.id, call.message.message_id, tg_id)

    elif data.startswith("lst_rjt_"):
        rid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id", (rid,))
        req = cursor.fetchone()
        if req:
            cursor.execute("SELECT fb_name FROM members WHERE telegram_id = %s", (req['telegram_id'],))
            mem = cursor.fetchone()
            conn.commit()
            st['exp_tc'].discard(rid)
            if mem: st['proc_msgs'].append(f"{mem['fb_name']} - Application Rejected❌\n\n")
            try: bot.send_message(req['telegram_id'], "Your request to change your Team has been Failed❌")
            except: pass
        conn.close()
        render_pend_tc_list(call.message.chat.id, call.message.message_id, tg_id)

    # Members List Dropdown Logic
    elif data.startswith("in_ad_t_"):
        t = data.split("_")[3]
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, full_name, unique_id, security_code, team_name FROM members WHERE team_name = %s AND status = 'Approved' AND is_blocked = FALSE AND is_removed = FALSE", (f"Team {t}",))
        mems = cursor.fetchall()
        conn.close()
        
        text_parts = []
        for m in mems:
            if m['telegram_id'] in st['exp_mem']:
                t_disp = str(m['team_name']).replace("Team ", "")
                prof = (f"👤Profile Summary\n"
                        f"FB Name: {m['fb_name']}\n"
                        f"Full Name: {m['full_name']}\n"
                        f"Unique ID: {m['unique_id']}\n"
                        f"Team: {t_disp}\n"
                        f"🫆Security Code: {m['security_code']}\n\n")
                text_parts.append(prof)
        
        kb = InlineKeyboardMarkup(row_width=1)
        if not mems: kb.add(InlineKeyboardButton("No Members Found", callback_data="ignore"))
        else:
            for m in mems:
                if m['telegram_id'] in st['exp_mem']:
                    kb.add(InlineKeyboardButton(f"{m['fb_name']} 🔻", callback_data=f"mem_col_{m['telegram_id']}_{t}"))
                else:
                    kb.add(InlineKeyboardButton(f"{m['fb_name']} 🔺", callback_data=f"mem_exp_{m['telegram_id']}_{t}"))
                    
        kb.row(InlineKeyboardButton("Back", callback_data="ad_back_mem"), InlineKeyboardButton("Cancel", callback_data="ad_cancel_msg"))
        final_text = "".join(text_parts).strip() if text_parts else "Select a member to view details:"
        bot.edit_message_text(final_text, call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif data.startswith("mem_exp_"):
        uid = int(data.split("_")[2])
        t_slug = data.split("_")[3]
        if len(st['exp_mem']) >= 3: st['exp_mem'].pop()
        st['exp_mem'].add(uid)
        call.data = f"in_ad_t_{t_slug}"
        callbacks(call)
        
    elif data.startswith("mem_col_"):
        uid = int(data.split("_")[2])
        t_slug = data.split("_")[3]
        st['exp_mem'].discard(uid)
        call.data = f"in_ad_t_{t_slug}"
        callbacks(call)

# 📩 Catch-all
@bot.message_handler(func=lambda message: True)
def handle_all_other(message):
    if enforce_registration(message): return
    bot.send_message(message.chat.id, "Select an option:", reply_markup=main_menu(message.from_user.id))

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True 
    t.start()
    print("🤖 KBKh Registration Bot is Running...")
    try:
        bot.remove_webhook()
        time.sleep(2) 
    except Exception: pass

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception:
            time.sleep(5)
