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
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

# 🏢 Teams Mapping (Database compatibility)
INFO_TEAMS = ["Team Alpha", "Team Beta", "Team Gamma"]
MEME_TEAMS = ["Team Electron", "Team Proton", "Team Neutron"]

user_temp_data = {}

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
            if is_blocked or status == "Blocked": return "Blocked"
            if is_removed or status == "Removed": return "UNREGISTERED"
            return status
        return "UNREGISTERED"
    except Exception:
        return "UNREGISTERED"

# 📱 Keyboards
def main_menu(user_id):
    status = get_user_status(user_id)
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if status == "ADMIN":
        markup.add(KeyboardButton("Pending Applications"), KeyboardButton("Members List"))
    elif status == "Approved":
        markup.add(KeyboardButton("My Profile"), KeyboardButton("Change Fb Name"), KeyboardButton("Request Team Change"))
    elif status == "Pending":
        markup.add(KeyboardButton("🔄 Refresh Status"))
    elif status == "Blocked":
        return None
    else:
        markup.add(KeyboardButton("Registration Now"), KeyboardButton("Already Registered"))
    return markup

def cancel_only_kb():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Cancel"))
    return markup

def back_cancel_kb():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))
    return markup

def team_select_kb():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(KeyboardButton("Alpha"), KeyboardButton("Beta"), KeyboardButton("Gamma"))
    markup.add(KeyboardButton("Electron"), KeyboardButton("Proton"), KeyboardButton("Neutron"))
    markup.add(KeyboardButton("Back"), KeyboardButton("Cancel"))
    return markup

def submit_cancel_kb():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("Submit"), KeyboardButton("Cancel"))
    return markup

def cancel_process(message):
    tg_id = message.from_user.id
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_temp_data.pop(tg_id, None)
    bot.send_message(message.chat.id, "Process Cancelled✅", reply_markup=main_menu(tg_id))

# 📌 /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status == "Blocked":
        bot.send_message(message.chat.id, "Access Blocked⛔")
        return
    text = "Welcome to KBKh Science Ecosystem!"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(tg_id))

# 🔄 Refresh Status
@bot.message_handler(func=lambda msg: msg.text == "🔄 Refresh Status")
def check_status_refresh(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status == "Pending":
        bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
    elif status == "Approved":
        bot.send_message(message.chat.id, "Registration approval was successful!✅", reply_markup=main_menu(tg_id))
    else:
        bot.send_message(message.chat.id, "Menu updated.", reply_markup=main_menu(tg_id))

# 📝 1. NEW REGISTRATION FLOW
@bot.message_handler(func=lambda msg: msg.text == "Registration Now")
def reg_start(message):
    tg_id = message.from_user.id
    status = get_user_status(tg_id)
    if status in ["Blocked", "Pending", "Approved"]:
        return bot.send_message(message.chat.id, "Action not allowed.", reply_markup=main_menu(tg_id))
    
    user_temp_data[tg_id] = {}
    msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_only_kb())
    bot.register_next_step_handler(msg, reg_full_name)

def reg_full_name(message):
    if message.text == "Cancel": return cancel_process(message)
    tg_id = message.from_user.id
    user_temp_data[tg_id]['fb'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=back_cancel_kb())
    bot.register_next_step_handler(msg, reg_unique_id)

def reg_unique_id(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Back":
        msg = bot.send_message(message.chat.id, "Enter Your Facebook Profile Name", reply_markup=cancel_only_kb())
        bot.register_next_step_handler(msg, reg_full_name)
        return
    user_temp_data[tg_id]['full'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Enter Your Unique ID (Given by Team)", reply_markup=back_cancel_kb())
    bot.register_next_step_handler(msg, reg_team)

def reg_team(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Back":
        msg = bot.send_message(message.chat.id, "Enter Your Full Name In English", reply_markup=back_cancel_kb())
        bot.register_next_step_handler(msg, reg_unique_id)
        return
    user_temp_data[tg_id]['uid'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "Select Your Team", reply_markup=team_select_kb())
    bot.register_next_step_handler(msg, reg_confirm)

def reg_confirm(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Back":
        msg = bot.send_message(message.chat.id, "Enter Your Unique ID (Given by Team)", reply_markup=back_cancel_kb())
        bot.register_next_step_handler(msg, reg_team)
        return
    
    team = message.text.strip()
    valid_teams = ["Alpha", "Beta", "Gamma", "Electron", "Proton", "Neutron"]
    if team not in valid_teams:
        msg = bot.send_message(message.chat.id, "Select Your Team", reply_markup=team_select_kb())
        bot.register_next_step_handler(msg, reg_confirm)
        return
    
    team_full = f"Team {team}"
    uid = user_temp_data[tg_id]['uid']
    cat_teams = INFO_TEAMS if team_full in INFO_TEAMS else MEME_TEAMS
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM members WHERE LOWER(unique_id) = LOWER(%s) AND team_name = ANY(%s) AND status != 'Removed'", (uid, cat_teams))
        exists_count = cursor.fetchone()[0]
        conn.close()
        
        if exists_count > 0:
            msg = bot.send_message(message.chat.id, "⚠️ Invalid Unique Id\n\nEnter Your Unique ID (Given by Team)", reply_markup=back_cancel_kb())
            bot.register_next_step_handler(msg, reg_team)
            return
            
        user_temp_data[tg_id]['team_full'] = team_full
        user_temp_data[tg_id]['team_short'] = team
        
        summary = (f"👤Your KBKh Profile Summary\n\n"
                   f"FB Name: {user_temp_data[tg_id]['fb']}\n"
                   f"Full Name: {user_temp_data[tg_id]['full']}\n"
                   f"Unique ID: {uid}\n"
                   f"Team: {team}\n\n"
                   f"Please recheck your final profile")
        
        msg = bot.send_message(message.chat.id, summary, reply_markup=submit_cancel_kb())
        bot.register_next_step_handler(msg, reg_submit_final)
    except Exception as e:
        bot.send_message(message.chat.id, "Error processing request.", reply_markup=main_menu(tg_id))

def reg_submit_final(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Submit":
        data = user_temp_data.get(tg_id, {})
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE telegram_id = %s", (tg_id,))
            cursor.execute("INSERT INTO members (telegram_id, fb_name, full_name, unique_id, team_name, user_type, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", 
                           (tg_id, data.get('fb'), data.get('full'), data.get('uid'), data.get('team_full'), 'General Member'))
            conn.commit()
            conn.close()
            
            bot.send_message(message.chat.id, "✅ Registration Request Submitted!\n\nYour application has been placed on admin pending!", reply_markup=main_menu(tg_id))
            user_temp_data.pop(tg_id, None)
        except Exception:
            bot.send_message(message.chat.id, "Submission Failed ❌", reply_markup=main_menu(tg_id))

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
            bot.send_message(message.chat.id, "Registration approval was successful!✅", reply_markup=main_menu(tg_id))
        else:
            conn.close()
            msg = bot.send_message(message.chat.id, "Failed ❌ Invalid Code. Enter your security code to restore your account.", reply_markup=cancel_only_kb())
            bot.register_next_step_handler(msg, process_recovery)
    except Exception:
        bot.send_message(message.chat.id, "Process Failed ❌", reply_markup=main_menu(tg_id))

# 👤 3. MY PROFILE
@bot.message_handler(func=lambda msg: msg.text == "My Profile")
def view_profile(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, security_code FROM members WHERE telegram_id = %s", (tg_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            fb, full, uid, team, code = user
            team_disp = str(team).replace("Team ", "")
            profile_msg = (f"👤Your KBKh Profile Summary\n\n"
                           f"FB Name: {fb}\n"
                           f"Full Name: {full}\n"
                           f"Unique ID: {uid}\n"
                           f"Team: {team_disp}\n"
                           f"🫆Security Code: {code}")
            bot.send_message(message.chat.id, profile_msg, reply_markup=main_menu(tg_id))
    except Exception:
        pass

# 🔄 4. CHANGE FB NAME
@bot.message_handler(func=lambda msg: msg.text == "Change Fb Name")
def change_fb_start(message):
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
    msg = bot.send_message(message.chat.id, f"New Fb Name: {message.text.strip()}\n\nClick submit to confirm", reply_markup=submit_cancel_kb())
    bot.register_next_step_handler(msg, process_fb_submit)

def process_fb_submit(message):
    tg_id = message.from_user.id
    if message.text == "Cancel": return cancel_process(message)
    if message.text == "Submit":
        new_fb = user_temp_data.get(tg_id, {}).get('new_fb', '')
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT fb_name FROM members WHERE telegram_id = %s", (tg_id,))
            old_fb = cursor.fetchone()[0]
            cursor.execute("INSERT INTO fb_name_requests (telegram_id, old_name, new_name, status) VALUES (%s, %s, %s, 'Pending')", (tg_id, old_fb, new_fb))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, "✅ FB Name Change Request Submitted!\n\nYour application has been placed on admin pending!", reply_markup=main_menu(tg_id))
        except Exception:
            bot.send_message(message.chat.id, "Failed ❌", reply_markup=main_menu(tg_id))

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
    kb.add(InlineKeyboardButton("Submit", callback_data="tc_submit"), InlineKeyboardButton("Cancel", callback_data="tc_cancel"))
    return kb

@bot.message_handler(func=lambda msg: msg.text == "Request Team Change")
def tc_start(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) != "Approved": return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM team_change_requests WHERE telegram_id = %s AND status = 'Pending'", (tg_id,))
        if cursor.fetchone():
            conn.close()
            return bot.send_message(message.chat.id, "Status: Pending⏳", reply_markup=main_menu(tg_id))
        cursor.execute("SELECT team_name FROM members WHERE telegram_id = %s", (tg_id,))
        current = cursor.fetchone()[0]
        conn.close()
        
        user_temp_data[tg_id] = {'current_team': current, 'selected_tc': None}
        bot.send_message(message.chat.id, "Select Team", reply_markup=get_tc_inline_kb(current))
    except Exception: pass

# 👑 ADMIN PANEL
@bot.message_handler(func=lambda msg: msg.text == "Pending Applications")
def admin_pend(message):
    tg_id = message.from_user.id
    if str(tg_id) != ADMIN_CHAT_ID: return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'Pending'")
        c1 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM fb_name_requests WHERE status = 'Pending'")
        c2 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM team_change_requests WHERE status = 'Pending'")
        c3 = cursor.fetchone()[0]
        conn.close()
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(f"Registration Application - {c1}", callback_data="ad_p_reg"),
               InlineKeyboardButton(f"Fb Name Change Application - {c2}", callback_data="ad_p_fb"),
               InlineKeyboardButton(f"Team Change Application - {c3}", callback_data="ad_p_tc"),
               InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
        bot.send_message(message.chat.id, "Pending Applications:", reply_markup=kb)
    except Exception: pass

@bot.message_handler(func=lambda msg: msg.text == "Members List")
def admin_mem_list(message):
    tg_id = message.from_user.id
    if str(tg_id) != ADMIN_CHAT_ID: return
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("Alpha", callback_data="ad_t_Alpha"), InlineKeyboardButton("Beta", callback_data="ad_t_Beta"), InlineKeyboardButton("Gamma", callback_data="ad_t_Gamma"))
    kb.add(InlineKeyboardButton("Electron", callback_data="ad_t_Electron"), InlineKeyboardButton("Proton", callback_data="ad_t_Proton"), InlineKeyboardButton("Neutron", callback_data="ad_t_Neutron"))
    kb.add(InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
    bot.send_message(message.chat.id, "Members List", reply_markup=kb)

# 🔘 INLINE CALLBACKS
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    tg_id = call.from_user.id
    data = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass

    # User Team Change Logic
    if data.startswith("tc_sel_"):
        t = data.split("_")[2]
        curr = user_temp_data.get(tg_id, {}).get('current_team')
        user_temp_data[tg_id]['selected_tc'] = t
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_tc_inline_kb(curr, t))
    
    elif data == "tc_cancel":
        bot.edit_message_text("Process Cancelled✅", call.message.chat.id, call.message.message_id)
        
    elif data == "tc_submit":
        sel = user_temp_data.get(tg_id, {}).get('selected_tc')
        curr = user_temp_data.get(tg_id, {}).get('current_team')
        if not sel or f"Team {sel}" == curr: return
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO team_change_requests (telegram_id, old_team, requested_team, status) VALUES (%s, %s, %s, 'Pending')", (tg_id, curr, f"Team {sel}"))
            conn.commit()
            conn.close()
            bot.edit_message_text("✅ Team Change Request Submitted!\n\nYour application has been placed on admin pending!", call.message.chat.id, call.message.message_id)
        except Exception: pass

    # Admin Panel Nav
    elif data == "ad_cancel":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif data == "ad_p_reg":
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE status = 'Pending'")
        reqs = cursor.fetchall()
        conn.close()
        
        bot.delete_message(call.message.chat.id, call.message.message_id)
        for r in reqs:
            t_disp = str(r['team_name']).replace("Team ", "")
            text = f"👤New Registration:\n\nFB: {r['fb_name']}\nFull Name: {r['full_name']}\nID: {r['unique_id']}\nTeam: {t_disp}\nTG ID: {r['telegram_id']}"
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Approve", callback_data=f"ap_r_{r['telegram_id']}"), InlineKeyboardButton("Reject", callback_data=f"rj_r_{r['telegram_id']}"))
            bot.send_message(call.message.chat.id, text, reply_markup=kb)
        
        b_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
        bot.send_message(call.message.chat.id, "Navigation:", reply_markup=b_kb)
        
    elif data == "ad_p_fb":
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM fb_name_requests WHERE status = 'Pending'")
        reqs = cursor.fetchall()
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)
        for r in reqs:
            text = f"👤FB Name Change:\n\nOld FB: {r['old_name']}\nNew FB: {r['new_name']}\nTG ID: {r['telegram_id']}"
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Approve", callback_data=f"ap_f_{r['id']}"), InlineKeyboardButton("Reject", callback_data=f"rj_f_{r['id']}"))
            bot.send_message(call.message.chat.id, text, reply_markup=kb)
        b_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
        bot.send_message(call.message.chat.id, "Navigation:", reply_markup=b_kb)
        
    elif data == "ad_p_tc":
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM team_change_requests WHERE status = 'Pending'")
        reqs = cursor.fetchall()
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)
        for r in reqs:
            text = f"👤Team Change:\n\nOld Team: {str(r['old_team']).replace('Team ','')}\nNew Team: {str(r['requested_team']).replace('Team ','')}\nTG ID: {r['telegram_id']}"
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Approve", callback_data=f"ap_t_{r['id']}"), InlineKeyboardButton("Reject", callback_data=f"rj_t_{r['id']}"))
            bot.send_message(call.message.chat.id, text, reply_markup=kb)
        b_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data="ad_back_pend"), InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
        bot.send_message(call.message.chat.id, "Navigation:", reply_markup=b_kb)
        
    elif data == "ad_back_pend":
        admin_pend(call.message)
        bot.delete_message(call.message.chat.id, call.message.message_id)

    # Admin Approve/Reject Logic
    elif data.startswith("ap_r_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        code = generate_security_code(conn)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE members SET status = 'Approved', security_code = %s WHERE telegram_id = %s RETURNING full_name, team_name", (code, uid))
        user = cursor.fetchone()
        conn.commit()
        conn.close()
        bot.edit_message_text("Registration approval was successful!✅", call.message.chat.id, call.message.message_id)
        if user:
            t_disp = str(user['team_name']).replace("Team ", "")
            msg = f"Registration approval was successful!✅\n\nWelcome {user['full_name']}!\n\nTeam: {t_disp}\n\nYour Security Code: {code}\n\n⚠️Please do not share you security code with anyone."
            try: bot.send_message(uid, msg, reply_markup=main_menu(uid))
            except: pass
            
    elif data.startswith("rj_r_"):
        uid = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM members WHERE telegram_id = %s", (uid,))
        conn.commit()
        conn.close()
        bot.edit_message_text("Registration Failed ❌", call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, "Registration Failed ❌\nPlease Try Again.", reply_markup=main_menu(uid))
        except: pass

    elif data.startswith("ap_f_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, new_name", (req_id,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET fb_name = %s WHERE telegram_id = %s", (req['new_name'], req['telegram_id']))
            conn.commit()
            bot.edit_message_text("Approved✅", call.message.chat.id, call.message.message_id)
            try: bot.send_message(req['telegram_id'], f"Your request to change your FB Name has been approved✅\n\nNew FB Name: {req['new_name']}", reply_markup=main_menu(req['telegram_id']))
            except: pass
        conn.close()
        
    elif data.startswith("rj_f_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE fb_name_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id", (req_id,))
        req = cursor.fetchone()
        conn.commit()
        conn.close()
        bot.edit_message_text("Failed ❌", call.message.chat.id, call.message.message_id)
        if req:
            try: bot.send_message(req['telegram_id'], "Your request to change your FB Name has been Failed ❌", reply_markup=main_menu(req['telegram_id']))
            except: pass

    elif data.startswith("ap_t_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Approved' WHERE id = %s RETURNING telegram_id, requested_team", (req_id,))
        req = cursor.fetchone()
        if req:
            cursor.execute("UPDATE members SET team_name = %s WHERE telegram_id = %s", (req['requested_team'], req['telegram_id']))
            conn.commit()
            t_disp = str(req['requested_team']).replace("Team ", "")
            bot.edit_message_text("Approved✅", call.message.chat.id, call.message.message_id)
            try: bot.send_message(req['telegram_id'], f"Your request to change your Team has been approved✅\n\nNew Team: {t_disp}", reply_markup=main_menu(req['telegram_id']))
            except: pass
        conn.close()
        
    elif data.startswith("rj_t_"):
        req_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE team_change_requests SET status = 'Rejected' WHERE id = %s RETURNING telegram_id", (req_id,))
        req = cursor.fetchone()
        conn.commit()
        conn.close()
        bot.edit_message_text("Failed ❌", call.message.chat.id, call.message.message_id)
        if req:
            try: bot.send_message(req['telegram_id'], "Your request to change your Team has been Failed ❌", reply_markup=main_menu(req['telegram_id']))
            except: pass

    # Admin Member List Logic
    elif data == "ad_back_teams":
        admin_mem_list(call.message)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif data.startswith("ad_t_"):
        t = data.split("_")[2]
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT full_name, telegram_id FROM members WHERE team_name = %s AND status = 'Approved'", (f"Team {t}",))
        mems = cursor.fetchall()
        conn.close()
        
        kb = InlineKeyboardMarkup(row_width=1)
        for m in mems:
            kb.add(InlineKeyboardButton(m['full_name'], callback_data=f"ad_m_{m['telegram_id']}_{t}"))
        kb.add(InlineKeyboardButton("Back", callback_data="ad_back_teams"), InlineKeyboardButton("Cancel", callback_data="ad_cancel"))
        bot.edit_message_text(f"{t} Members:", call.message.chat.id, call.message.message_id, reply_markup=kb)
        
    elif data.startswith("ad_m_"):
        uid = int(data.split("_")[2])
        t_slug = data.split("_")[3]
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (uid,))
        u = cursor.fetchone()
        conn.close()
        
        if u:
            t_disp = str(u['team_name']).replace("Team ", "")
            text = f"👤Registration Information:\n\nFB: {u['fb_name']}\nFull Name: {u['full_name']}\nID: {u['unique_id']}\nTeam: {t_disp}\nTG ID: {u['telegram_id']}\n🫆Security Code: {u['security_code']}"
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data=f"ad_t_{t_slug}"))
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)

# 📩 Catch-all
@bot.message_handler(func=lambda message: True)
def handle_all_other(message):
    tg_id = message.from_user.id
    if get_user_status(tg_id) == "Blocked": return
    bot.send_message(message.chat.id, "Menu", reply_markup=main_menu(tg_id))

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
