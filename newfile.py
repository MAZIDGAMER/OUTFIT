import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters,
    ChatMemberHandler,
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

# إعداد الـ logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# الثوابت
API_BASE_URL = "https://iridudishrudks.vercel.app/accinfo"
FOX_API_URL = "https://fox-api-lyart.vercel.app/info?id={uid}"
CHANNEL_ID = -1002444229316
CHANNEL_LINK = "https://t.me/l7aj_ff_group"
BOT_TOKEN = "5175709686:AAEs5-jvaCRmoEK8d0Ix8GUHj2ze3uJ0Abk"
MAPPING_FILE = "/storage/emulated/0/mapping.txt"

# المتغيرات العامة
user_languages = {}
ALLOWED_REGIONS = ["mea", "IND", "br", "cis", "eu", "id", "bd", "na", "sac", "pk", "sg", "th", "tw", "us", "vn"]

# --- الدوال المساعدة ---

def load_mapping(file_path):
    mapping_data = {}
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    parts = line.strip().split("/")
                    if len(parts) == 3:
                        item_id, image_code, name = parts
                        mapping_data[item_id] = {"image_code": image_code, "name": name}
    except Exception as e:
        logger.error(f"Error loading mapping file: {e}")
    return mapping_data

mapping_data = load_mapping(MAPPING_FILE)

def is_valid_region(region):
    return region.lower() in [r.lower() for r in ALLOWED_REGIONS]

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def fetch_data(uid, region):
    api_url = f"{API_BASE_URL}?uid={uid}&region={region}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                response.raise_for_status()
                data = await response.json()
                if "ID" in data:
                    return {"AccountProfileInfo": {"EquippedOutfit": data["ID"]}}
                return None
    except Exception as e:
        logger.error(f"Error fetching data for region {region}: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def fetch_player_info(uid):
    api_url = FOX_API_URL.format(uid=uid)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get('basicInfo', {}).get('nickname', uid)
    except Exception as e:
        logger.error(f"Error fetching player info: {e}")
        return uid

async def download_images(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [download_single_image(session, url) for url in urls]
        return await asyncio.gather(*tasks)

async def download_single_image(session, url):
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            img = Image.open(BytesIO(await response.read()))
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            return img
    except Exception as e:
        logger.warning(f"Error downloading image {url}: {e}")
        return None

async def is_user_in_channel(user_id, bot):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

async def update_loading_message(message, user_language):
    dots = ["", "●", "●●", "●●●"]
    while True:
        for dot in dots:
            await message.edit_text(f"⏳ جاري التحقق{dot}" if user_language == "ar" else f"⏳ Checking{dot}")
            await asyncio.sleep(0.5)

# --- معالجات الأوامر ---

async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    keyboard = [
        [InlineKeyboardButton("العربية", callback_data="set_language_ar"),
         InlineKeyboardButton("English", callback_data="set_language_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 مرحباً! اختر لغتك / Welcome! Choose your language:", reply_markup=reply_markup)

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == "set_language_ar":
        user_languages[user_id] = "ar"
        await query.answer("تم تعيين اللغة إلى العربية.")
    elif query.data == "set_language_en":
        user_languages[user_id] = "en"
        await query.answer("Language set to English.")

    user_language = user_languages.get(user_id, "ar")
    if query.message.chat.type == "private":
        await query.message.reply_text(
            "⚠️ مرحبا بك في بوت L7 out FF! ⚠️\n\n"
            "🚨 البوت يعمل فقط في هاذه المجموعة .\n\n"
            "🔹 انضم إلى المجموعة هنا:\n\n https://t.me/l7aj_ff_group" 
            if user_language == "ar" else 
            "⚠️ Welcome to the L7 out FF bot! ⚠️\n\n"
            "🚨 The bot only works in this group.\n\n"
            "🔹 Join the group here:\n\n https://t.me/l7aj_ff_group"
        )
    else:
        await query.message.reply_text(
            "✅ تم تحديث اللغة.\nالآن أرسل /out تم معرفك لتحصل على قائمة أمنيتك.\n /out 1234567 \n\n By : @l7l7aj" 
            if user_language == "ar" else 
            "✅ Language updated.\nNow send /out and your UID to get your Wish out.\n /out 1234567 \n\n By : @l7l7aj"
        )

async def out_command(update: Update, context: CallbackContext):
    if update.message.chat.type == "private":
        await update.message.reply_text("⚠️ هذا البوت يعمل فقط في المجموعة.")
        return

    text = update.message.text.strip().split()
    user_language = user_languages.get(update.message.from_user.id, "ar")

    if len(text) == 2:
        uid = text[1]
        region = None
    elif len(text) == 3:
        region = text[1].lower()
        uid = text[2]
        
        if not is_valid_region(region):
            await update.message.reply_text(
                "⚠️ المنطقة المدخلة غير صحيحة. يرجى استخدام واحدة من المناطق التالية:\n"
                "mea, IND, br, cis, eu, id, bd, na, sac, pk, sg, th, tw, us, vn" 
                if user_language == "ar" else
                "⚠️ Invalid region. Please use one of these regions:\n"
                "mea, IND, br, cis, eu, id, bd, na, sac, pk, sg, th, tw, us, vn"
            )
            return
    else:
        await update.message.reply_text(
            "⚠️ يرجى إدخال الأمر بالشكل الصحيح:\n"
            "/out معرف_اللاعب\n"
            "أو\n"
            "/out المنطقة معرف_اللاعب\n"
            "مثال:\n"
            "/out 12345678\n"
            "/out ind 12345678" 
            if user_language == "ar" else
            "⚠️ Please use the correct format:\n"
            "/out player_id\n"
            "or\n"
            "/out region player_id\n"
            "Examples:\n"
            "/out 12345678\n"
            "/out ind 12345678"
        )
        return

    message = await update.message.reply_text("⏳ جاري التحقق..." if user_language == "ar" else "⏳ Checking...")
    loading_task = asyncio.create_task(update_loading_message(message, user_language))

    nickname = await fetch_player_info(uid)
    data = None

    if region:
        data = await fetch_data(uid, region)
    else:
        for r in ALLOWED_REGIONS:
            data = await fetch_data(uid, r)
            if data and "AccountProfileInfo" in data:
                break

    if not data or "AccountProfileInfo" not in data:
        loading_task.cancel()
        await update.message.reply_text(
            "❌ حدث خطأ أثناء جلب البيانات. قد يكون المعرف خاطئاً أو اللاعب ليس لديه عناصر." 
            if user_language == "ar" else 
            "❌ Error fetching data. The ID may be wrong or the player has no items."
        )
        return

    equipped_outfit = data["AccountProfileInfo"].get("EquippedOutfit", [])
    if not equipped_outfit:
        loading_task.cancel()
        await update.message.reply_text(
            "❌ لم يتم العثور على أي عناصر." 
            if user_language == "ar" else 
            "❌ No items found."
        )
        return

    image_urls = []
    captions = []
    for item_id in equipped_outfit:
        item_id_str = str(item_id)
        if item_id_str in mapping_data:
            image_code = mapping_data[item_id_str]["image_code"]
            name = mapping_data[item_id_str]["name"]
            image_url = f"https://freefiremobile-a.akamaihd.net/common/Local/PK/FF_UI_Icon/{image_code}.png"
            image_urls.append(image_url)
            captions.append(name)

    images = await download_images(image_urls)
    base_image_url = "https://g.top4top.io/p_3374s0emv0.jpg"
    base_image = await download_single_image(aiohttp.ClientSession(), base_image_url)
    
    if not base_image:
        loading_task.cancel()
        await update.message.reply_text(
            "❌ فشل تحميل الصورة الأساسية." 
            if user_language == "ar" else 
            "❌ Failed to load base image."
        )
        return

    coordinates = [
        (50, 50), (30, 560), (100, 910), 
        (560, 970),
        (925, 10), (975, 360), (935, 880)
    ]
    box_size = (300, 300)
    image_size = (300, 300)

    canvas = base_image.copy()
    for i, img in enumerate(images[:7]):  # نأخذ أول 6 صور فقط لتتناسب مع الإحداثيات
        if img:
            img = img.resize(image_size, Image.LANCZOS)
            x, y = coordinates[i]
            x_center = x + (box_size[0] - image_size[0]) // 2
            y_center = y + (box_size[1] - image_size[1]) // 2
            canvas.paste(img, (x_center, y_center), img)

    byte_io = BytesIO()
    canvas.save(byte_io, format="PNG")
    byte_io.seek(0)

    region_info = f"\n🌍 المنطقة: {region.upper()}" if region else ""
    caption = "\n".join(captions[:7])  # نأخذ أول 6 عناصر فقط
    
    await update.message.reply_photo(
        photo=byte_io,
        caption=f"👤 اسم اللاعب: {nickname}{region_info}\n🎮 العناصر المجهزة:\n{caption}\n\nBy: @l7l7aj" 
        if user_language == "ar" else 
        f"👤 Player Name: {nickname}{region_info}\n🎮 Equipped Items:\n{caption}\n\nBy: @l7l7aj"
    )

    loading_task.cancel()
    await message.delete()

async def handle_chat_member_update(update: Update, context: CallbackContext):
    user_id = update.chat_member.new_chat_member.user.id
    status = update.chat_member.new_chat_member.status
    user_language = user_languages.get(user_id, "ar")

    if status in ['member', 'administrator', 'creator']:
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ لقد انضممت إلى القناة! يمكنك الآن استخدام البوت." 
            if user_language == "ar" else
            "✅ You have joined the channel! You can now use the bot."
        )
    elif status == 'left':
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ لقد غادرت القناة! لم يعد بإمكانك استخدام البوت." 
            if user_language == "ar" else
            "❌ You have left the channel! You can no longer use the bot."
        )

async def ignore_other_messages(update: Update, context: CallbackContext):
    if update.message.chat.type != "private" and not update.message.text.startswith("/out"):
        return

# --- التشغيل الرئيسي ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("out", out_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore_other_messages))
    application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    application.run_polling()

if __name__ == "__main__":
    main()