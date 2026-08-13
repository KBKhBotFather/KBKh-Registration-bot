import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URI = os.getenv("DB_URI")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Conversation States
FULL_NAME, FB_NAME, FB_LINK, SECURITY_CODE, LOGIN_CODE = range(5)

# Database Helper
def get_db_connection():
    return psycopg2.connect(DB_URI, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            full_name TEXT,
            fb_name TEXT,
            fb_link TEXT,
            security_code TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_user(telegram_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE telegram_id = %s;", (telegram_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def save_user(telegram_id, full_name, fb_name, fb_link, security_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, full_name, fb_name, fb_link, security_code, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
        ON CONFLICT (telegram_id) DO UPDATE 
        SET full_name = EXCLUDED.full_name,
            fb_name = EXCLUDED.fb_name,
            fb_link = EXCLUDED.fb_link,
            security_code = EXCLUDED.security_code,
            status = 'pending';
    """, (telegram_id, full_name, fb_name, fb_link, security_code))
    conn.commit()
    cur.close()
    conn.close()

def update_user_status(telegram_id, status):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET status = %s WHERE telegram_id = %s;", (status, telegram_id))
    conn.commit()
    cur.close()
    conn.close()

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user:
        if user['status'] == 'pending':
            await update.message.reply_text(
                "⚠️ আপনার রেজিস্ট্রেশন অনুরোধ বর্তমানে পেন্ডিং (Pending) রয়েছে।\n"
                "এডমিন আপনার তথ্য রিভিউ করে এপ্রুভ করার পর আপনাকে জানিয়ে দেওয়া হবে।"
            )
            return ConversationHandler.END
        elif user['status'] == 'approved':
            await update.message.reply_text(
                f"✅ স্বাগতম {user['full_name']}!\n"
                "আপনি একজন নিবন্ধিত সাধারণ মডারেটর।"
            )
            return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📝 Register", callback_data="btn_register")],
        [InlineKeyboardButton("🔐 Already Registered", callback_data="btn_already_registered")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 স্বাগতম KBKh Registration Bot-এ!\nনিচের যেকোনো একটি অপশন বেছে নিন:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = get_user(user_id)

    if query.data == "btn_register":
        if user and user['status'] == 'pending':
            await query.edit_message_text(
                "⚠️ আপনার রেজিস্ট্রেশন পেন্ডিং আছে। এডমিন অনুমোদন দেওয়া পর্যন্ত অপেক্ষা করুন।"
            )
            return ConversationHandler.END
        elif user and user['status'] == 'approved':
            await query.edit_message_text("✅ আপনি ইতিমধ্যে নিবন্ধিত মডারেটর!")
            return ConversationHandler.END

        await query.edit_message_text("Enter Your Full Name In English:")
        return FULL_NAME

    elif query.data == "btn_already_registered":
        await query.edit_message_text("Enter your security code:")
        return LOGIN_CODE

async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("Enter Your Facebook Profile Name:")
    return FB_NAME

async def get_fb_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fb_name'] = update.message.text.strip()
    await update.message.reply_text("Enter Your Facebook Profile Link:")
    return FB_LINK

async def get_fb_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fb_link'] = update.message.text.strip()
    await update.message.reply_text("একটি পাসওয়ার্ড/সিকিউরিটি কোড দিন (যেমন: 12345):")
    return SECURITY_CODE

async def get_security_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sec_code = update.message.text.strip()
    context.user_data['security_code'] = sec_code
    user_id = update.effective_user.id

    # Save to database
    save_user(
        telegram_id=user_id,
        full_name=context.user_data['full_name'],
        fb_name=context.user_data['fb_name'],
        fb_link=context.user_data['fb_link'],
        security_code=sec_code
    )

    await update.message.reply_text(
        "🎉 আপনার রেজিস্ট্রেশন সফলভাবে জমা হয়েছে!\n"
        "এডমিন অনুমোদন দিলে আপনাকে জানানো হবে।"
    )

    # Admin Notification
    if ADMIN_CHAT_ID:
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"admin_app_{user_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"admin_rej_{user_id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        admin_msg = (
            f"📥 **নতুন রেজিস্ট্রেশন আবেদন!**\n\n"
            f"👤 **Name:** {context.user_data['full_name']}\n"
            f"🔵 **FB Name:** {context.user_data['fb_name']}\n"
            f"🔗 **FB Link:** {context.user_data['fb_link']}\n"
            f"🔑 **Security Code:** {sec_code}\n"
            f"🆔 **Telegram ID:** `{user_id}`"
        )
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_markup
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    return ConversationHandler.END

async def process_login_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_code = update.message.text.strip()
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user and user['security_code'] == input_code:
        if user['status'] == 'approved':
            await update.message.reply_text(
                f"✅ সিকিউরিটি কোড সঠিক!\nস্বাগতম {user['full_name']}! আপনি একজন নিবন্ধিত মডারেটর।"
            )
        else:
            await update.message.reply_text("⚠️ আপনার সিকিউরিটি কোড সঠিক, তবে রেজিস্ট্রেশন এখনও পেন্ডিং রয়েছে।")
    else:
        await update.message.reply_text("❌ ভুল সিকিউরিটি কোড! আবার চেষ্টা করতে /start দিন।")

    return ConversationHandler.END

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("admin_app_"):
        target_id = int(data.replace("admin_app_", ""))
        update_user_status(target_id, 'approved')
        await query.edit_message_text(f"{query.message.text}\n\n✅ **Approved by Admin**", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 অভিনন্দন! এডমিন আপনার মডারেটর রেজিস্ট্রেশন এপ্রুভ করেছেন।"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    elif data.startswith("admin_rej_"):
        target_id = int(data.replace("admin_rej_", ""))
        update_user_status(target_id, 'rejected')
        await query.edit_message_text(f"{query.message.text}\n\n❌ **Rejected by Admin**", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ দুঃখিত, আপনার রেজিস্ট্রেশন আবেদনটি বাতিল করা হয়েছে।"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে। /start চেপে আবার চেষ্টা করুন।")
    return ConversationHandler.END

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_click, pattern="^(btn_register|btn_already_registered)$")
        ],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            FB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fb_name)],
            FB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fb_link)],
            SECURITY_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_security_code)],
            LOGIN_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_login_code)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(admin_app_|admin_rej_)"))

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
