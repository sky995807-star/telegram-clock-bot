import os, sqlite3
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN=os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_IDS={int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()}
TZ=ZoneInfo(os.getenv("TIMEZONE","Asia/Taipei"))
WORK_START=time.fromisoformat(os.getenv("WORK_START","09:00"))
DB_PATH=os.getenv("DB_PATH","attendance.db")

def conn():
    c=sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS employees(
      user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,name TEXT,
      action TEXT,timestamp TEXT,late INTEGER DEFAULT 0)""")
    c.commit(); return c

def now(): return datetime.now(TZ)
def late(dt): return int(dt.time()>WORK_START)
def kb(): return ReplyKeyboardMarkup([["🟢 上班打卡","🔴 下班打卡"],["📅 我的紀錄","ℹ️ 說明"]],resize_keyboard=True)
def admin(uid): return uid in ADMIN_IDS

async def start(u,c):
    await u.message.reply_text("歡迎使用群組打卡機器人，請選擇操作。",reply_markup=kb())

async def punch(u,action):
    user=u.effective_user; dt=now(); db=conn()
    emp=db.execute("SELECT active,name FROM employees WHERE user_id=?",(user.id,)).fetchone()
    if not emp or not emp[0]:
        db.close(); await u.message.reply_text("⛔ 你尚未被管理員加入員工名單。"); return
    islate=late(dt) if action=="上班" else 0
    db.execute("INSERT INTO attendance(user_id,name,action,timestamp,late) VALUES(?,?,?,?,?)",
      (user.id,emp[1],action,dt.isoformat(timespec="seconds"),islate))
    db.commit(); db.close()
    await u.message.reply_text(f"✅ {action}打卡成功{'（遲到）' if islate else ''}\n時間：{dt:%Y-%m-%d %H:%M:%S}")

async def mine(u):
    db=conn(); rows=db.execute("SELECT action,timestamp,late FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 10",(u.effective_user.id,)).fetchall(); db.close()
    await u.message.reply_text("📅 最近紀錄：\n"+"\n".join(f"{datetime.fromisoformat(t):%m-%d %H:%M}｜{a}{'（遲到）' if l else ''}" for a,t,l in rows) if rows else "目前沒有紀錄。")

async def add(u,c):
    if not admin(u.effective_user.id): return await u.message.reply_text("⛔ 無權限")
    if len(c.args)<2: return await u.message.reply_text("格式：/add 員工TelegramID 姓名")
    uid=int(c.args[0]); name=" ".join(c.args[1:]); db=conn()
    db.execute("INSERT OR REPLACE INTO employees(user_id,name,active) VALUES(?,?,1)",(uid,name)); db.commit(); db.close()
    await u.message.reply_text(f"✅ 已加入：{name}")

async def remove(u,c):
    if not admin(u.effective_user.id): return await u.message.reply_text("⛔ 無權限")
    if not c.args: return await u.message.reply_text("格式：/remove 員工TelegramID")
    db=conn(); db.execute("UPDATE employees SET active=0 WHERE user_id=?",(int(c.args[0]),)); db.commit(); db.close()
    await u.message.reply_text("✅ 已停用員工")

async def report(u,c):
    if not admin(u.effective_user.id): return await u.message.reply_text("⛔ 無權限")
    db=conn(); rows=db.execute("SELECT name,action,timestamp,late FROM attendance ORDER BY id DESC LIMIT 100").fetchall(); db.close()
    await u.message.reply_text("📊 紀錄：\n"+"\n".join(f"{datetime.fromisoformat(t):%m-%d %H:%M}｜{n}｜{a}{'（遲到）' if l else ''}" for n,a,t,l in rows) or "沒有資料")

async def stats(u,c):
    if not admin(u.effective_user.id): return await u.message.reply_text("⛔ 無權限")
    d=now().date().isoformat(); db=conn()
    present={r[0] for r in db.execute("SELECT DISTINCT user_id FROM attendance WHERE action='上班' AND timestamp LIKE ?",(d+"%",))}
    employees={r[0]:r[1] for r in db.execute("SELECT user_id,name FROM employees WHERE active=1")}
    late_count=db.execute("SELECT COUNT(*) FROM attendance WHERE action='上班' AND late=1 AND timestamp LIKE ?",(d+"%",)).fetchone()[0]
    db.close(); absent=[name for uid,name in employees.items() if uid not in present]
    await u.message.reply_text(f"📈 今日 {d}\n已打卡：{len(present)}\n遲到：{late_count}\n缺勤（未上班打卡）：{len(absent)}\n"+("缺勤名單："+ "、".join(absent) if absent else "缺勤名單：無"))

async def msg(u,c):
    t=u.message.text
    if t=="🟢 上班打卡": await punch(u,"上班")
    elif t=="🔴 下班打卡": await punch(u,"下班")
    elif t=="📅 我的紀錄": await mine(u)
    elif t=="ℹ️ 說明": await u.message.reply_text("上班時間："+WORK_START.strftime("%H:%M")+"\n管理員指令：/add /remove /report /stats")

app=Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("add",add))
app.add_handler(CommandHandler("remove",remove)); app.add_handler(CommandHandler("report",report))
app.add_handler(CommandHandler("stats",stats))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,msg))
app.run_polling()
