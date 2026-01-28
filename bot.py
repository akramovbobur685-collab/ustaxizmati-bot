import asyncio
import re
import sqlite3
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ----------------- SETTINGS -----------------
TOKEN = "7849457113:AAGsuBHsCJ5HlA3PEuyOfpWt9Mh7t3-IB0A"  # tokenni o'zing qo'yasan
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ustaxizmati.db"

PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{7,}$")

# ADMIN: avval /myid bilan ID ni ol, keyin shu yerga qo'y
ADMIN_IDS = {1019797279}

# Buttons
BTN_USTA = "🧑‍🔧 Men ustaman"
BTN_BUYURT = "🏠 Men buyurtmachiman"
BTN_LIST = "📋 Ustalar ro‘yxati"
BTN_MY_PROFILE = "👤 Profilim"
BTN_EDIT_PROFILE = "✏️ Profilni tahrirlash"
BTN_ACTIVE = "✅ Faol"
BTN_INACTIVE = "⛔️ Nofaol"
BTN_FREE = "🟢 Bo‘shman"
BTN_BUSY = "🔴 Bandman"
BTN_BACK = "⬅️ Asosiy menyu"
BTN_CANCEL = "❌ Bekor qilish"

# Admin buttons
BTN_ADMIN = "🛡 Admin panel"
BTN_ADMIN_USTALAR = "📋 Admin: Ustalar"
BTN_ADMIN_BUYURTMALAR = "🧾 Admin: Buyurtmalar"
BTN_ADMIN_BLOCK = "🚫 Admin: Bloklash (ID)"
BTN_ADMIN_UNBLOCK = "✅ Admin: Aktivlash (ID)"
BTN_ADMIN_BACK = "⬅️ Admin: Orqaga"

# ----------------- BOT INIT -----------------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ----------------- DB HELPERS -----------------
def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _try_exec(cur: sqlite3.Cursor, sql: str):
    try:
        cur.execute(sql)
    except Exception:
        pass

def init_db_sync() -> None:
    conn = db_connect()
    cur = conn.cursor()

    # ustalar: status + is_active qo'shildi
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ustalar (
        user_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        job TEXT NOT NULL,
        region TEXT NOT NULL,
        status TEXT DEFAULT '🟢 Bo‘shman',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    """)

    # eski db bo'lsa, ustiga column qo'shib qo'yamiz (agar yo'q bo'lsa)
    _try_exec(cur, "ALTER TABLE ustalar ADD COLUMN status TEXT DEFAULT '🟢 Bo‘shman';")
    _try_exec(cur, "ALTER TABLE ustalar ADD COLUMN is_active INTEGER DEFAULT 1;")

    # ✅ buyurtmalar: qabul qilish uchun status/accepted_by/accepted_at qo‘shildi
    cur.execute("""
    CREATE TABLE IF NOT EXISTS buyurtmalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ish_turi TEXT NOT NULL,
        region TEXT NOT NULL,
        phone TEXT NOT NULL,
        comment TEXT DEFAULT '',
        status TEXT DEFAULT 'new',
        accepted_by INTEGER,
        accepted_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    # eski db bo'lsa ham qo‘shib qo‘yamiz
    _try_exec(cur, "ALTER TABLE buyurtmalar ADD COLUMN status TEXT DEFAULT 'new';")
    _try_exec(cur, "ALTER TABLE buyurtmalar ADD COLUMN accepted_by INTEGER;")
    _try_exec(cur, "ALTER TABLE buyurtmalar ADD COLUMN accepted_at TEXT;")

    conn.commit()
    conn.close()

async def init_db() -> None:
    await asyncio.to_thread(init_db_sync)

def upsert_usta_sync(user_id: int, name: str, phone: str, job: str, region: str) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO ustalar(user_id, name, phone, job, region, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(user_id) DO UPDATE SET
        name=excluded.name,
        phone=excluded.phone,
        job=excluded.job,
        region=excluded.region,
        updated_at=datetime('now');
    """, (user_id, name, phone, job, region))
    conn.commit()
    conn.close()

async def upsert_usta(user_id: int, name: str, phone: str, job: str, region: str) -> None:
    await asyncio.to_thread(upsert_usta_sync, user_id, name, phone, job, region)

def get_usta_sync(user_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ustalar WHERE user_id=?;", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

async def get_usta(user_id: int) -> Optional[sqlite3.Row]:
    return await asyncio.to_thread(get_usta_sync, user_id)

def set_usta_status_sync(user_id: int, status: str) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE ustalar SET status=?, updated_at=datetime('now') WHERE user_id=?;", (status, user_id))
    conn.commit()
    conn.close()

async def set_usta_status(user_id: int, status: str) -> None:
    await asyncio.to_thread(set_usta_status_sync, user_id, status)

def set_usta_active_sync(user_id: int, is_active: int) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE ustalar SET is_active=?, updated_at=datetime('now') WHERE user_id=?;", (is_active, user_id))
    conn.commit()
    conn.close()

async def set_usta_active(user_id: int, is_active: int) -> None:
    await asyncio.to_thread(set_usta_active_sync, user_id, is_active)

def list_ustalar_sync(limit: int = 30) -> List[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, name, phone, job, region, status, is_active, updated_at
        FROM ustalar
        ORDER BY updated_at DESC
        LIMIT ?;
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

async def list_ustalar(limit: int = 30) -> List[sqlite3.Row]:
    return await asyncio.to_thread(list_ustalar_sync, limit)

def insert_buyurtma_sync(user_id: int, ish_turi: str, region: str, phone: str, comment: str) -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO buyurtmalar(user_id, ish_turi, region, phone, comment)
    VALUES (?, ?, ?, ?, ?);
    """, (user_id, ish_turi, region, phone, comment))
    conn.commit()
    bid = cur.lastrowid
    conn.close()
    return bid

async def insert_buyurtma(user_id: int, ish_turi: str, region: str, phone: str, comment: str) -> int:
    return await asyncio.to_thread(insert_buyurtma_sync, user_id, ish_turi, region, phone, comment)

def list_buyurtmalar_sync(limit: int = 30) -> List[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, ish_turi, region, phone, comment, created_at
        FROM buyurtmalar
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

async def list_buyurtmalar(limit: int = 30) -> List[sqlite3.Row]:
    return await asyncio.to_thread(list_buyurtmalar_sync, limit)

def find_matching_ustalar_sync(ish_turi: str, region: str, limit: int = 10) -> List[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
    SELECT user_id, name, phone, job, region, status
    FROM ustalar
    WHERE is_active=1
      AND lower(job) LIKE '%' || lower(?) || '%'
      AND lower(region) LIKE '%' || lower(?) || '%'
    ORDER BY updated_at DESC
    LIMIT ?;
    """, (ish_turi, region, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

async def find_matching_ustalar(ish_turi: str, region: str, limit: int = 10) -> List[sqlite3.Row]:
    return await asyncio.to_thread(find_matching_ustalar_sync, ish_turi, region, limit)

# ✅ BUYURTMA QABUL QILISH (DB)
def accept_buyurtma_sync(order_id: int, usta_id: int) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE buyurtmalar
        SET status='accepted', accepted_by=?, accepted_at=datetime('now')
        WHERE id=? AND status='new';
    """, (usta_id, order_id))
    ok = cur.rowcount == 1
    conn.commit()
    conn.close()
    return ok

async def accept_buyurtma(order_id: int, usta_id: int) -> bool:
    return await asyncio.to_thread(accept_buyurtma_sync, order_id, usta_id)

def get_buyurtma_sync(order_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM buyurtmalar WHERE id=?;", (order_id,))
    row = cur.fetchone()
    conn.close()
    return row

async def get_buyurtma(order_id: int) -> Optional[sqlite3.Row]:
    return await asyncio.to_thread(get_buyurtma_sync, order_id)

# ----------------- UI -----------------
def main_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_USTA)],
        [KeyboardButton(text=BTN_BUYURT)],
        [KeyboardButton(text=BTN_LIST)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def nav_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True
    )

def usta_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MY_PROFILE), KeyboardButton(text=BTN_EDIT_PROFILE)],
            [KeyboardButton(text=BTN_FREE), KeyboardButton(text=BTN_BUSY)],
            [KeyboardButton(text=BTN_ACTIVE), KeyboardButton(text=BTN_INACTIVE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True
    )

def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADMIN_USTALAR)],
            [KeyboardButton(text=BTN_ADMIN_BUYURTMALAR)],
            [KeyboardButton(text=BTN_ADMIN_BLOCK)],
            [KeyboardButton(text=BTN_ADMIN_UNBLOCK)],
            [KeyboardButton(text=BTN_ADMIN_BACK)],
        ],
        resize_keyboard=True
    )

# ----------------- STATES -----------------
class UstaReg(StatesGroup):
    name = State()
    phone = State()
    job = State()
    region = State()

class BuyurtmachiReg(StatesGroup):
    ish_turi = State()
    region = State()
    phone = State()
    comment = State()

class AdminFlow(StatesGroup):
    block_id = State()
    unblock_id = State()

# ----------------- HELPERS -----------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def send_order_to_ustalar(order_id: int, ish_turi: str, region: str, phone: str, comment: str, ustalar_rows: List[sqlite3.Row]):
    # Ustalarga avtomatik yuborish (limit 10)
    text = (
        "🆕 Yangi buyurtma!\n\n"
        f"ID: {order_id}\n"
        f"Kerak: {ish_turi}\n"
        f"Hudud: {region}\n"
        f"Buyurtmachi tel: {phone}\n"
    )
    if comment:
        text += f"Izoh: {comment}\n"
    text += "\nQabul qilish uchun tugmani bosing:"

    # ✅ Qabul qildim tugmasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Qabul qildim", callback_data=f"accept:{order_id}")]
    ])

    for u in ustalar_rows[:10]:
        try:
            await bot.send_message(u["user_id"], text, reply_markup=kb)
        except Exception:
            pass

# ✅ CALLBACK: usta "Qabul qildim" bosganda
@dp.callback_query(F.data.startswith("accept:"))
async def accept_callback(cb: CallbackQuery, state: FSMContext):
    try:
        order_id = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("Xato ID", show_alert=True)
        return

    usta_id = cb.from_user.id

    # usta ro'yxatdan o'tganmi
    usta = await get_usta(usta_id)
    if not usta:
        await cb.answer("Avval usta sifatida ro'yxatdan o'ting.", show_alert=True)
        return

    ok = await accept_buyurtma(order_id, usta_id)
    if not ok:
        await cb.answer("Bu buyurtma allaqachon qabul qilingan.", show_alert=True)
        return

    order = await get_buyurtma(order_id)
    if not order:
        await cb.answer("Buyurtma topilmadi.", show_alert=True)
        return

    buyer_id = int(order["user_id"])

    # Buyurtmachiga usta kontaktini yuboramiz
    msg_buyer = (
        "✅ Buyurtmangiz qabul qilindi!\n\n"
        f"Buyurtma ID: {order_id}\n"
        f"Usta: {usta['name']}\n"
        f"Tel: {usta['phone']}\n"
        f"Kasb: {usta['job']}\n"
        f"Hudud: {usta['region']}\n"
    )
    try:
        await bot.send_message(buyer_id, msg_buyer)
    except Exception:
        pass

    # Ustaga tasdiq
    await cb.answer("Qabul qilindi ✅")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(f"✅ Siz buyurtmani qabul qildingiz. (ID: {order_id})")

# ----------------- BASIC COMMANDS -----------------
@dp.message(Command("myid"))
async def myid(message: Message):
    await message.answer(f"Sizning ID: {message.from_user.id}")

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer(
        "Assalomu alaykum 👋\n\nUstaxizmati botiga xush kelibsiz!\nKim sifatida kirmoqchisiz?",
        reply_markup=main_kb(is_admin=is_admin(uid))
    )

# ----------------- NAV HANDLERS -----------------
@dp.message(F.text == BTN_CANCEL)
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi. Asosiy menyu:", reply_markup=main_kb(is_admin=is_admin(message.from_user.id)))

@dp.message(F.text == BTN_BACK)
async def back_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Asosiy menyu:", reply_markup=main_kb(is_admin=is_admin(message.from_user.id)))

# ----------------- LIST USTALAR -----------------
@dp.message(F.text == BTN_LIST)
async def ustalar_list(message: Message, state: FSMContext):
    await state.clear()
    rows = await list_ustalar(30)
    if not rows:
        await message.answer("📋 Hozircha ustalar ro‘yxati bo‘sh.", reply_markup=main_kb(is_admin=is_admin(message.from_user.id)))
        return
    text = "📋 Ustalar ro‘yxati:\n"
    for r in rows:
        active = "✅" if r["is_active"] == 1 else "⛔️"
        text += f"• {active} {r['status']} {r['name']} | {r['job']} | {r['region']} | {r['phone']}\n"
    await message.answer(text, reply_markup=main_kb(is_admin=is_admin(message.from_user.id)))

# ----------------- USTA CABINET -----------------
@dp.message(F.text == BTN_USTA)
async def usta_entry(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    row = await get_usta(uid)
    if row:
        await message.answer("🧑‍🔧 Usta kabinetiga xush kelibsiz!", reply_markup=usta_kb())
    else:
        await state.set_state(UstaReg.name)
        await message.answer("🧑‍🔧 Usta ro‘yxatdan o‘tish.\nIsmingizni yuboring:", reply_markup=nav_kb())

@dp.message(F.text == BTN_MY_PROFILE)
async def usta_profile(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    row = await get_usta(uid)
    if not row:
        await message.answer("Avval ro‘yxatdan o‘ting: 🧑‍🔧 Men ustaman", reply_markup=main_kb(is_admin=is_admin(uid)))
        return
    active = "✅ Faol" if row["is_active"] == 1 else "⛔️ Nofaol"
    await message.answer(
        "👤 Profil:\n\n"
        f"Ism: {row['name']}\n"
        f"Tel: {row['phone']}\n"
        f"Kasb: {row['job']}\n"
        f"Hudud: {row['region']}\n"
        f"Holat: {row['status']}\n"
        f"Status: {active}\n",
        reply_markup=usta_kb()
    )

@dp.message(F.text == BTN_EDIT_PROFILE)
async def usta_edit(message: Message, state: FSMContext):
    await state.set_state(UstaReg.name)
    await message.answer("✏️ Profilni tahrirlash.\nYangi ismingizni yuboring:", reply_markup=nav_kb())

@dp.message(F.text == BTN_FREE)
async def usta_free(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if not await get_usta(uid):
        await message.answer("Avval ro‘yxatdan o‘ting: 🧑‍🔧 Men ustaman", reply_markup=main_kb(is_admin=is_admin(uid)))
        return
    await set_usta_status(uid, "🟢 Bo‘shman")
    await message.answer("Holat yangilandi: 🟢 Bo‘shman", reply_markup=usta_kb())

@dp.message(F.text == BTN_BUSY)
async def usta_busy(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if not await get_usta(uid):
        await message.answer("Avval ro‘yxatdan o‘ting: 🧑‍🔧 Men ustaman", reply_markup=main_kb(is_admin=is_admin(uid)))
        return
    await set_usta_status(uid, "🔴 Bandman")
    await message.answer("Holat yangilandi: 🔴 Bandman", reply_markup=usta_kb())

@dp.message(F.text == BTN_ACTIVE)
async def usta_active(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if not await get_usta(uid):
        await message.answer("Avval ro‘yxatdan o‘ting: 🧑‍🔧 Men ustaman", reply_markup=main_kb(is_admin=is_admin(uid)))
        return
    await set_usta_active(uid, 1)
    await message.answer("✅ Endi siz FAOLsiz (buyurtmalar keladi).", reply_markup=usta_kb())

@dp.message(F.text == BTN_INACTIVE)
async def usta_inactive(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if not await get_usta(uid):
        await message.answer("Avval ro‘yxatdan o‘ting: 🧑‍🔧 Men ustaman", reply_markup=main_kb(is_admin=is_admin(uid)))
        return
    await set_usta_active(uid, 0)
    await message.answer("⛔️ Endi siz NOFAOLsiz (buyurtma kelmaydi).", reply_markup=usta_kb())

# ----------------- USTA REG FLOW -----------------
@dp.message(UstaReg.name)
async def usta_name(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Ism juda qisqa. Qayta yozing:", reply_markup=nav_kb())
        return
    await state.update_data(name=name)
    await state.set_state(UstaReg.phone)
    await message.answer("📞 Telefon raqamingiz (masalan: +998901234567):", reply_markup=nav_kb())

@dp.message(UstaReg.phone)
async def usta_phone(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    phone = (message.text or "").strip()
    if not PHONE_RE.match(phone):
        await message.answer("Telefon noto‘g‘ri. Masalan: +998901234567\nQayta yuboring:", reply_markup=nav_kb())
        return
    await state.update_data(phone=phone)
    await state.set_state(UstaReg.job)
    await message.answer("🛠 Kasbingiz (Elektrik / Santexnik / Payvandchi ...):", reply_markup=nav_kb())

@dp.message(UstaReg.job)
async def usta_job(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    job = (message.text or "").strip()
    if len(job) < 3:
        await message.answer("Kasb juda qisqa. Qayta yozing:", reply_markup=nav_kb())
        return
    await state.update_data(job=job)
    await state.set_state(UstaReg.region)
    await message.answer("📍 Hudud (masalan: Andijon, Asaka):", reply_markup=nav_kb())

@dp.message(UstaReg.region)
async def usta_region(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    region = (message.text or "").strip()
    if len(region) < 2:
        await message.answer("Hudud noto‘g‘ri. Qayta yozing:", reply_markup=nav_kb())
        return

    data = await state.get_data()
    uid = message.from_user.id
    await upsert_usta(uid, data["name"], data["phone"], data["job"], region)
    await state.clear()

    await message.answer(
        "✅ Usta profil saqlandi!\n\n"
        f"Ism: {data['name']}\n"
        f"Tel: {data['phone']}\n"
        f"Kasb: {data['job']}\n"
        f"Hudud: {region}\n\n"
        "Kabinet: 👤 Profilim",
        reply_markup=usta_kb()
    )

# ----------------- BUYURTMACHI FLOW -----------------
@dp.message(F.text == BTN_BUYURT)
async def buyurt_start(message: Message, state: FSMContext):
    await state.set_state(BuyurtmachiReg.ish_turi)
    await message.answer("🏠 Buyurtma qoldirish.\nQanday usta kerak? (Elektrik / Santexnik):", reply_markup=nav_kb())

@dp.message(BuyurtmachiReg.ish_turi)
async def buyurt_ish_turi(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    ish = (message.text or "").strip()
    if len(ish) < 3:
        await message.answer("Ish turi juda qisqa. Qayta yozing:", reply_markup=nav_kb())
        return
    await state.update_data(ish_turi=ish)
    await state.set_state(BuyurtmachiReg.region)
    await message.answer("📍 Hududingiz (masalan: Shahrixon):", reply_markup=nav_kb())

@dp.message(BuyurtmachiReg.region)
async def buyurt_region(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    region = (message.text or "").strip()
    if len(region) < 2:
        await message.answer("Hudud noto‘g‘ri. Qayta yozing:", reply_markup=nav_kb())
        return
    await state.update_data(region=region)
    await state.set_state(BuyurtmachiReg.phone)
    await message.answer("📞 Telefon raqamingiz (masalan: +998901234567):", reply_markup=nav_kb())

@dp.message(BuyurtmachiReg.phone)
async def buyurt_phone(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    phone = (message.text or "").strip()
    if not PHONE_RE.match(phone):
        await message.answer("Telefon noto‘g‘ri. Masalan: +998901234567\nQayta yuboring:", reply_markup=nav_kb())
        return
    await state.update_data(phone=phone)
    await state.set_state(BuyurtmachiReg.comment)
    await message.answer("📝 Izoh (ixtiyoriy). Yo‘q bo‘lsa `-` yuboring:", reply_markup=nav_kb())

@dp.message(BuyurtmachiReg.comment)
async def buyurt_finish(message: Message, state: FSMContext):
    if message.text in (BTN_BACK, BTN_CANCEL):
        return
    comment = (message.text or "").strip()
    if comment == "-":
        comment = ""

    data = await state.get_data()
    uid = message.from_user.id

    order_id = await insert_buyurtma(uid, data["ish_turi"], data["region"], data["phone"], comment)
    moslar = await find_matching_ustalar(data["ish_turi"], data["region"], 10)

    msg = (
        f"✅ Buyurtma qabul qilindi! (ID: {order_id})\n\n"
        f"Kerak: {data['ish_turi']}\n"
        f"Hudud: {data['region']}\n"
        f"Tel: {data['phone']}\n"
    )
    if comment:
        msg += f"Izoh: {comment}\n"

    if moslar:
        msg += "\n🔎 Mos ustalar:\n"
        for u in moslar:
            msg += f"• {u['status']} {u['name']} | {u['job']} | {u['region']} | {u['phone']}\n"
        msg += "\n✅ Buyurtma mos ustalarga ham yuborildi (Qabul qildim tugmasi bilan)."
        await send_order_to_ustalar(order_id, data["ish_turi"], data["region"], data["phone"], comment, moslar)
    else:
        msg += "\nHozircha mos usta topilmadi. Ish turi yoki hududni aniqroq yozib ko‘ring."

    await state.clear()
    await message.answer(msg, reply_markup=main_kb(is_admin=is_admin(uid)))

# ----------------- ADMIN PANEL (sening kodinging qolgan qismi) -----------------
@dp.message(F.text == BTN_ADMIN)
async def admin_panel(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_admin(uid):
        await message.answer("Bu bo‘lim faqat admin uchun.", reply_markup=main_kb(is_admin=False))
        return
    await state.clear()
    await message.answer("🛡 Admin panel:", reply_markup=admin_kb())

@dp.message(F.text == BTN_ADMIN_BACK)
async def admin_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_kb(is_admin=True))

@dp.message(F.text == BTN_ADMIN_USTALAR)
async def admin_ustalar(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    rows = await list_ustalar(50)
    if not rows:
        await message.answer("Ustalar yo‘q.", reply_markup=admin_kb())
        return
    text = "📋 Admin: Ustalar (oxirgi 50)\n"
    for r in rows:
        active = "✅" if r["is_active"] == 1 else "⛔️"
        text += f"{r['user_id']} | {active} {r['status']} {r['name']} | {r['job']} | {r['region']} | {r['phone']}\n"
    await message.answer(text, reply_markup=admin_kb())

@dp.message(F.text == BTN_ADMIN_BUYURTMALAR)
async def admin_buyurtmalar(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    rows = await list_buyurtmalar(50)
    if not rows:
        await message.answer("Buyurtmalar yo‘q.", reply_markup=admin_kb())
        return
    text = "🧾 Admin: Buyurtmalar (oxirgi 50)\n"
    for r in rows:
        text += f"ID:{r['id']} | user:{r['user_id']} | {r['ish_turi']} | {r['region']} | {r['phone']} | {r['created_at']}\n"
    await message.answer(text, reply_markup=admin_kb())

@dp.message(F.text == BTN_ADMIN_BLOCK)
async def admin_block_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminFlow.block_id)
    await message.answer("🚫 Bloklash uchun usta user_id yuboring:", reply_markup=admin_kb())

@dp.message(AdminFlow.block_id)
async def admin_block_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int((message.text or "").strip())
    except:
        await message.answer("ID raqam bo‘lishi kerak. Qayta yuboring:", reply_markup=admin_kb())
        return
    await set_usta_active(uid, 0)
    await state.clear()
    await message.answer(f"✅ {uid} bloklandi (nofaol).", reply_markup=admin_kb())

@dp.message(F.text == BTN_ADMIN_UNBLOCK)
async def admin_unblock_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminFlow.unblock_id)
    await message.answer("✅ Aktivlash uchun usta user_id yuboring:", reply_markup=admin_kb())

@dp.message(AdminFlow.unblock_id)
async def admin_unblock_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int((message.text or "").strip())
    except:
        await message.answer("ID raqam bo‘lishi kerak. Qayta yuboring:", reply_markup=admin_kb())
        return
    await set_usta_active(uid, 1)
    await state.clear()
    await message.answer(f"✅ {uid} aktiv qilindi (faol).", reply_markup=admin_kb())

# ----------------- FALLBACK -----------------
@dp.message()
async def fallback(message: Message):
    await message.answer("Menyudan tanlang 🙂", reply_markup=main_kb(is_admin=is_admin(message.from_user.id)))

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
