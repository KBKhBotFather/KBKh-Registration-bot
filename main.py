import logging
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import psycopg2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Render Port Binding
def run_dummy_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
  server.serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = os.environ.get("ADMIN_ID")


def get_db_connection():
  return psycopg2.connect(DATABASE_URL, sslmode="require")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user

  # মেম্বার আগে থেকে রেজিস্টার্ড কি না চেক করা
  conn = get_db_connection()
  cur = conn.cursor()
  cur.execute(
      "SELECT status FROM members WHERE telegram_id = %s", (user.id,)
  )
  res = cur.fetchone()
  conn.close()

  if res:
    status = res[0]
    if status == "Approved":
      await update.message.reply_text(
          "✅ আপনি ইতিমধ্যেই অনুমোদিত (Approved) সদস্য!"
      )
    elif status == "Pending":
      await update.message.reply_text(
          "⏳ আপনার রেজিস্ট্রেশন আবেদনটি এখনও এডমিন অনুমোদনের অপেক্ষায় আছে।"
      )
    elif status == "Blocked":
      await update.message.reply_text("⛔ আপনাকে ব্লক করা হয়েছে।")
    return

  await update.message.reply_text(
      f"👋 **KBKh Registration Portal**-এ স্বাগতম, {user.first_name}!\n\n"
      "রেজিস্ট্রেশন সম্পূর্ণ করতে আপনার **Facebook Name**টি লিখে পাঠান:"
  )
  context.user_data["step"] = "FB_NAME"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  step = context.user_data.get("step")
  text = update.message.text.strip()
  user = update.effective_user

  if step == "FB_NAME":
    context.user_data["fb_name"] = text
    await update.message.reply_text("ধন্যবাদ! এবার আপনার **পুরো নাম (Full Name)** লিখুন:")
    context.user_data["step"] = "FULL_NAME"

  elif step == "FULL_NAME":
    context.user_data["full_name"] = text

    keyboard = [
        [InlineKeyboardButton("Info Team", callback_data="team_Info Team")],
        [InlineKeyboardButton("Meme Team", callback_data="team_Meme Team")],
    ]
    await update.message.reply_text(
        "আপনার **টিম (Team)** নির্বাচন করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    context.user_data["step"] = "TEAM"


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  if query.data.startswith("team_"):
    team_name = query.data.split("_")[1]
    user = update.effective_user

    fb_name = context.user_data.get("fb_name", user.first_name)
    full_name = context.user_data.get("full_name", user.full_name)

    # Neon DB-তে Pending স্ট্যাটাসে সেভ করা
    try:
      conn = get_db_connection()
      cur = conn.cursor()
      cur.execute(
          """
                INSERT INTO members (telegram_id, fb_name, full_name, team_name, status)
                VALUES (%s, %s, %s, %s, 'Pending')
                ON CONFLICT (telegram_id) DO UPDATE 
                SET fb_name = EXCLUDED.fb_name, full_name = EXCLUDED.full_name, team_name = EXCLUDED.team_name, status = 'Pending';
            """,
          (user.id, fb_name, full_name, team_name),
      )
      conn.commit()
      conn.close()

      await query.edit_message_text(
          "🎉 **রেজিস্ট্রেশন আবেদন সফলভাবে জমা হয়েছে!**\n\n"
          "এডমিন রিভিউ করে অনুমোদন দিলে আপনি বটের সকল সুবিধা ব্যবহার করতে পারবেন।"
      )

      # এডমিনকে কন্ট্রোল রুমে দেখার নোটিফিকেশন পাঠানো
      if ADMIN_ID:
        try:
          await context.bot.send_message(
              chat_id=ADMIN_ID,
              text=(
                  f"📥 **নতুন রেজিস্ট্রেশন আবেদন!**\n\n"
                  f"👤 **নাম:** {full_name}\n"
                  f"🔗 **FB Name:** {fb_name}\n"
                  f"📌 **টিম:** {team_name}\n\n"
                  f"কন্ট্রোল রুম বটের `📋 Pending Approvals` অপশনে গিয়ে Approve"
                  " করতে পারেন।"
              ),
          )
        except Exception as e:
          logger.error(f"Admin Notify Error: {e}")

    except Exception as e:
      await query.edit_message_text(f"❌ ডাটা সেভ করতে সমস্যা হয়েছে: {e}")


def main():
  if not BOT_TOKEN:
    return
  app = Application.builder().token(BOT_TOKEN).build()

  app.add_handler(CommandHandler("start", start))
  app.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )
  app.add_handler(CallbackQueryHandler(handle_callback))

  logger.info("Registration Bot Running...")
  app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
