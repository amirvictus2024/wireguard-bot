import logging
import os
import json
import random
import ipaddress
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from datetime import datetime

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = "7577432090:AAG9sN1ILuTsr8TDQwuBN-_nDWTTzfSUmVg"
ADMIN_ID = 7240662021
DB_FILE = "database.json"

# Function to check if user is an admin
def is_admin(user_id):
    db = load_database()
    admins = db['settings'].get('admins', [])
    return str(user_id) == str(ADMIN_ID) or str(user_id) in [str(admin) for admin in admins]

# States for conversation
MAIN_MENU, ADMIN_PANEL, ADD_BALANCE, BUY_CONFIG, SUPPORT, USER_ACCOUNT, LOCATION_SELECT, CONFIG_CONFIRM, REFERRAL, ABOUT_US = range(10)

# Default referral reward
DEFAULT_REFERRAL_REWARD = 2000

# Import location data from range.py
from range import LOCATIONS

# Card information for payments
CARD_NUMBER = "6219861943084037"
CARD_HOLDER = "نام و نام خانوادگی"

# Database initialization
def init_database():
    if not os.path.exists(DB_FILE):
        data = {
            'users': {},
            'configs': {},
            'settings': {
                'card_number': CARD_NUMBER,
                'card_holder': CARD_HOLDER,
                'referral_reward': DEFAULT_REFERRAL_REWARD
            }
        }
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    return load_database()

def load_database():
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_database(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user(user_id, data=None):
    if data is None:
        data = load_database()

    user_id_str = str(user_id)
    if user_id_str not in data['users']:
        data['users'][user_id_str] = {
            'balance': 0,
            'configs': [],
            'referral_code': f"REF{user_id_str[-5:]}_{random.randint(1000, 9999)}",
            'referred_by': None,
            'referrals': []
        }
        save_database(data)

    return data['users'][user_id_str]

# Keyboard Markups
def main_menu_keyboard(user_id=None):
    keyboard = [
        [
            InlineKeyboardButton("🚀 خرید کانفیگ", callback_data='buy_config')
        ],
        [
            InlineKeyboardButton("💰 افزایش موجودی", callback_data='add_balance'),
            InlineKeyboardButton("👤 حساب کاربری", callback_data='user_account')
        ],
        [
            InlineKeyboardButton("📞 پشتیبانی", callback_data='support'),
            InlineKeyboardButton("🎁 رفرال", callback_data='referral')
        ],
        [
            InlineKeyboardButton("ℹ️ درباره ما", callback_data='about_us')
        ]
    ]

    # Add admin panel button for admins
    if user_id and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ پنل مدیریت", callback_data='admin_panel')])

    return InlineKeyboardMarkup(keyboard)

def user_account_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 سرویس‌های من", callback_data='my_services')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("💳 تغییر اطلاعات کارت", callback_data='change_card'),
            InlineKeyboardButton("💸 افزایش موجودی کاربر", callback_data='add_user_balance')
        ],
        [
            InlineKeyboardButton("🖥️ مدیریت سرورها", callback_data='manage_servers'),
            InlineKeyboardButton("💰 تغییر قیمت سرورها", callback_data='change_server_prices')
        ],
        [
            InlineKeyboardButton("🔗 تغییر مبلغ رفرال", callback_data='change_referral_reward'),
            InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data='manage_admins')
        ],
        [
            InlineKeyboardButton("👤 مدیریت کاربران", callback_data='manage_users')
        ],
        [
            InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def location_keyboard():
    keyboard = []
    loc_items = [(loc_id, loc_info) for loc_id, loc_info in LOCATIONS.items() if loc_info['active']]

    # Put locations in pairs if possible
    for i in range(0, len(loc_items), 2):
        row = []
        for j in range(2):
            if i + j < len(loc_items):
                loc_id, loc_info = loc_items[i + j]
                row.append(InlineKeyboardButton(
                    f"{loc_info['name']} - {loc_info['price']} تومان", 
                    callback_data=f'loc_{loc_id}'
                ))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')])
    return InlineKeyboardMarkup(keyboard)

def manage_servers_keyboard():
    keyboard = []
    loc_items = list(LOCATIONS.items())

    # Put server management buttons in pairs
    for i in range(0, len(loc_items), 2):
        row = []
        for j in range(2):
            if i + j < len(loc_items):
                loc_id, loc_info = loc_items[i + j]
                status = "✅ فعال" if loc_info['active'] else "❌ غیرفعال"
                row.append(InlineKeyboardButton(
                    f"{loc_info['name']} - {status}", 
                    callback_data=f'toggle_server_{loc_id}'
                ))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')])
    return InlineKeyboardMarkup(keyboard)

# Import Wireguard config module
from wgconfig import generate_wireguard_config, get_config_caption

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Initialize user in database if needed
    data = load_database()
    user_data = get_user(user.id, data)
    
    # Check if user is blocked
    if user_data.get('is_blocked', False) and not is_admin(user.id):
        await update.message.reply_text(
            "🚫 حساب کاربری شما مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
        )
        return ConversationHandler.END

    # Check for referral code in start command
    if context.args and len(context.args) > 0:
        referral_code = context.args[0]

        # Only process if user hasn't been referred before
        if not user_data.get('referred_by'):
            # Find the user with this referral code
            referrer_id = None
            for uid, udata in data['users'].items():
                if udata.get('referral_code') == referral_code:
                    referrer_id = uid
                    break

            if referrer_id and referrer_id != str(user.id):  # Can't refer yourself
                # Get the referral reward amount
                referral_reward = data['settings'].get('referral_reward', DEFAULT_REFERRAL_REWARD)

                # Mark this user as referred
                user_data['referred_by'] = referrer_id

                # Add user to referrer's referrals list
                if 'referrals' not in data['users'][referrer_id]:
                    data['users'][referrer_id]['referrals'] = []

                if str(user.id) not in data['users'][referrer_id]['referrals']:
                    data['users'][referrer_id]['referrals'].append(str(user.id))

                # Add balance to referrer
                data['users'][referrer_id]['balance'] += referral_reward

                # Save changes
                save_database(data)

                # Notify referrer with more detailed message
                try:
                    referrer_old_balance = data['users'][referrer_id]['balance'] - referral_reward
                    referrer_new_balance = data['users'][referrer_id]['balance']

                    await context.bot.send_message(
                        chat_id=int(referrer_id),
                        text=f"🎁 تبریک! کاربر جدیدی با لینک رفرال شما عضو شد.\n\n"
                             f"👤 تعداد کل رفرال‌های شما: {len(data['users'][referrer_id]['referrals'])}\n"
                             f"💰 پاداش این رفرال: {referral_reward} تومان\n"
                             f"💳 موجودی قبلی: {referrer_old_balance} تومان\n"
                             f"💳 موجودی جدید: {referrer_new_balance} تومان\n\n"
                             f"🔄 با دعوت از دوستان خود موجودی خود را افزایش دهید!"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer {referrer_id}: {e}")

    welcome_text = f"سلام {user.first_name}!\n" \
                  "به ربات فروش کانفیگ وایرگارد خوش آمدید. " \
                  "از منوی زیر گزینه مورد نظر خود را انتخاب کنید:"

    # If user was referred, add a message
    if 'referred_by' in user_data and user_data['referred_by']:
        welcome_text += "\n\n🎁 شما با لینک دعوت وارد شده‌اید."

    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(user.id)
    )

    return MAIN_MENU

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id
    
    # Check if user is blocked (skip for admins and unblock actions)
    if not is_admin(user_id) and not data.startswith('unblock_user_'):
        db = load_database()
        user_data = get_user(user_id, db)
        if user_data.get('is_blocked', False):
            await query.edit_message_text(
                "🚫 حساب کاربری شما مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
            )
            return ConversationHandler.END

    # Main menu options
    if data == 'buy_config':
        await query.edit_message_text(
            "لطفا نوع لوکیشن مورد نظر خود را انتخاب کنید:",
            reply_markup=location_keyboard()
        )
        return LOCATION_SELECT

    elif data == 'referral':
        db = load_database()
        user = get_user(user_id, db)
        referral_code = user['referral_code']
        referral_reward = db['settings'].get('referral_reward', DEFAULT_REFERRAL_REWARD)

        referrals = user.get('referrals', [])
        referral_count = len(referrals)

        referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"

        await query.edit_message_text(
            f"🔗 سیستم رفرال\n\n"
            f"💎 به ازای هر دوست که با لینک دعوت شما عضو شود، {referral_reward} تومان به حساب شما اضافه می‌شود.\n\n"
            f"🔗 لینک رفرال شما:\n{referral_link}\n\n"
            f"📊 تعداد دعوت شده‌ها: {referral_count}\n"
            f"💰 درآمد از رفرال‌ها: {referral_count * referral_reward} تومان\n\n"
            f"⚠️ کاربران دعوت شده باید برای اولین بار با لینک شما وارد ربات شوند.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
        )
        return REFERRAL
        
    elif data == 'about_us':
        about_text = (
            "🎮 *خدمات گیمینگ وایرگارد ما*\n\n"
            "سلام به همه گیمرهای عزیز! 👋\n\n"
            "🔹 *سیستم هوشمند وایرگارد*\n"
            "ما ارائه‌دهنده کانفیگ‌های اختصاصی وایرگارد هستیم که با بهره‌گیری از فناوری نسل ششم اینترنت (IPv6)، "
            "تجربه‌ای منحصر به فرد را برای شما فراهم می‌کنیم.\n\n"
            "🎯 *مزایای ویژه*:\n"
            "• کاهش چشمگیر پینگ تا حد باورنکردنی ۲۰! 😮\n"
            "• تضمین رجیستر یا بازگشت کامل هزینه\n"
            "• قرارگیری در لابی‌های ایرانی در بیشتر بازی‌ها (در سرویس‌های نقره‌ای و طلایی)\n"
            "• پشتیبانی حرفه‌ای در تمام طول دوره اشتراک\n"
            "• سازگار با تمامی دستگاه‌ها (PC, Mobile, Console)\n\n"
            "📌 *نکات مهم*:\n"
            "• برای نسخه‌های غیراصلی مانند نسخه کره‌ای، تنها سرویس الماسی مؤثر است\n"
            "• تمامی سرویس‌ها کاملاً اختصاصی و بدون امکان تست هستند\n"
            "• خدمات ما تنها برای کاربران داخل ایران بهینه‌سازی شده است\n\n"
            "🏆 *معرفی سرویس‌ها*:\n\n"
            "🥇 *سرویس طلایی* - بهترین گزینه برای اینترنت‌های ضعیف‌تر\n"
            "🥈 *سرویس نقره‌ای* - مناسب برای اینترنت‌های استاندارد\n"
            "💎 *سرویس الماسی* - بهینه‌سازی شده برای سرورهای آمریکا، کره و نسخه‌های خاص\n\n"
            "هر دو سرویس طلایی و نقره‌ای در تمامی حالت‌های بازی (کلاسیک، TDM و...) در سرورهای آسیا، اروپا و خاورمیانه عملکرد عالی دارند.\n\n"
            "با ما تجربه گیمینگ خود را به سطح دیگری ارتقا دهید! 🚀"
        )
        
        try:
            await query.edit_message_text(
                about_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]]),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in displaying about us with Markdown: {e}")
            # در صورت مشکل با Markdown، متن را بدون فرمت نشان می‌دهیم
            await query.edit_message_text(
                "🎮 خدمات گیمینگ وایرگارد ما\n\n"
                "سلام به همه گیمرهای عزیز! 👋\n\n"
                "🔹 سیستم هوشمند وایرگارد\n"
                "ما ارائه‌دهنده کانفیگ‌های اختصاصی وایرگارد هستیم که با بهره‌گیری از فناوری نسل ششم اینترنت (IPv6)، "
                "تجربه‌ای منحصر به فرد را برای شما فراهم می‌کنیم.\n\n"
                "🎯 مزایای ویژه:\n"
                "• کاهش چشمگیر پینگ تا حد باورنکردنی ۲۰! 😮\n"
                "• تضمین رجیستر یا بازگشت کامل هزینه\n"
                "• قرارگیری در لابی‌های ایرانی در بیشتر بازی‌ها (در سرویس‌های نقره‌ای و طلایی)\n"
                "• پشتیبانی حرفه‌ای در تمام طول دوره اشتراک\n"
                "• سازگار با تمامی دستگاه‌ها (PC, Mobile, Console)\n\n"
                "📌 نکات مهم:\n"
                "• برای نسخه‌های غیراصلی مانند نسخه کره‌ای، تنها سرویس الماسی مؤثر است\n"
                "• تمامی سرویس‌ها کاملاً اختصاصی و بدون امکان تست هستند\n"
                "• خدمات ما تنها برای کاربران داخل ایران بهینه‌سازی شده است\n\n"
                "🏆 معرفی سرویس‌ها:\n\n"
                "🥇 سرویس طلایی - بهترین گزینه برای اینترنت‌های ضعیف‌تر\n"
                "🥈 سرویس نقره‌ای - مناسب برای اینترنت‌های استاندارد\n"
                "💎 سرویس الماسی - بهینه‌سازی شده برای سرورهای آمریکا، کره و نسخه‌های خاص\n\n"
                "هر دو سرویس طلایی و نقره‌ای در تمامی حالت‌های بازی (کلاسیک، TDM و...) در سرورهای آسیا، اروپا و خاورمیانه عملکرد عالی دارند.\n\n"
                "با ما تجربه گیمینگ خود را به سطح دیگری ارتقا دهید! 🚀",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
            )
            
        return ABOUT_US

    elif data == 'add_balance':
        db = load_database()
        card_number = db['settings'].get('card_number', CARD_NUMBER)
        card_holder = db['settings'].get('card_holder', 'نام و نام خانوادگی')

        # اسکیپ کاراکترهای خاص در فرمت Markdown
        special_chars = ['-', '.', '(', ')', '+', '_', '*', '[', ']', '~', '`', '>', '#', '=', '|', '{', '}', '!']
        escaped_card_number = card_number
        escaped_card_holder = card_holder

        for char in special_chars:
            escaped_card_number = escaped_card_number.replace(char, f'\\{char}')
            escaped_card_holder = escaped_card_holder.replace(char, f'\\{char}')


        # Create keyboard with preset amounts
        plans_keyboard = [
            [
                InlineKeyboardButton("💎 ۵۰ هزار تومان", callback_data='balance_plan_50000'),
                InlineKeyboardButton("💎 ۱۰۰ هزار تومان", callback_data='balance_plan_100000')
            ],
            [
                InlineKeyboardButton("💎 ۲۰۰ هزار تومان", callback_data='balance_plan_200000'),
                InlineKeyboardButton("💎 ۵۰۰ هزار تومان", callback_data='balance_plan_500000')
            ],
            [
                InlineKeyboardButton("💰 مبلغ دلخواه", callback_data='custom_balance')
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')
            ]
        ]

        try:
            await query.edit_message_text(
                f"💰 برای افزایش موجودی، لطفا یکی از مبالغ زیر را انتخاب کنید یا مبلغ دلخواه را وارد کنید:\n\n"
                f"💳 شماره کارت: `{escaped_card_number}`\n"
                f"👤 به نام: {escaped_card_holder}\n\n"
                "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                reply_markup=InlineKeyboardMarkup(plans_keyboard),
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Error in displaying card info: {e}")
            # Fallback to plain text if Markdown fails
            await query.edit_message_text(
                f"💰 برای افزایش موجودی، لطفا یکی از مبالغ زیر را انتخاب کنید یا مبلغ دلخواه را وارد کنید:\n\n"
                f"💳 شماره کارت: {card_number}\n"
                f"👤 به نام: {card_holder}\n\n"
                "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                reply_markup=InlineKeyboardMarkup(plans_keyboard)
            )

        return ADD_BALANCE

    elif data == 'user_account':
        db = load_database()
        user = get_user(user_id, db)

        configs_text = ""
        if user['configs']:
            configs_text = "\n\n📁 کانفیگ های شما:\n"
            for i, config_id in enumerate(user['configs'], 1):
                config = db['configs'][config_id]
                configs_text += f"{i}. {config['name']} - {config['type']}\n"

        await query.edit_message_text(
            f"👤 حساب کاربری شما\n\n"
            f"🪪 شناسه: {user_id}\n"
            f"💎 موجودی: {user['balance']} تومان"
            f"{configs_text}",
            reply_markup=user_account_keyboard()
        )
        return USER_ACCOUNT

    elif data == 'my_services':
        db = load_database()
        user = get_user(user_id, db)

        if not user['configs']:
            await query.edit_message_text(
                "📂 سرویس‌های من\n\n"
                "❌ شما هنوز هیچ سرویسی خریداری نکرده‌اید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='user_account')]])
            )
            return USER_ACCOUNT

        keyboard = []
        for config_id in user['configs']:
            config = db['configs'][config_id]
            keyboard.append([InlineKeyboardButton(
                f"{config['name']} - تاریخ انقضا: {config['expiry_date']}", 
                callback_data=f'show_config_{config_id}'
            )])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='user_account')])

        await query.edit_message_text(
            "📂 سرویس‌های من\n\n"
            "برای دریافت مجدد کانفیگ، روی آن کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return USER_ACCOUNT

    elif data.startswith('show_config_'):
        config_id = data.replace('show_config_', '')
        db = load_database()

        if config_id in db['configs']:
            config = db['configs'][config_id]

            # محاسبه زمان باقی‌مانده
            expiry_date = datetime.strptime(config['expiry_date'], '%Y-%m-%d')
            days_remaining = (expiry_date - datetime.now()).days
            remaining_text = f"{days_remaining} روز" if days_remaining > 0 else "منقضی شده"

            # ایجاد کپشن برای کانفیگ
            config_caption = f"🔄 دریافت مجدد کانفیگ\n\n" \
                            f"🔰 نوع سرویس: {config['name']}\n" \
                            f"📆 تاریخ انقضا: {config['expiry_date']}\n" \
                            f"⏱️ زمان باقی‌مانده: {remaining_text}"

            try:
                # ارسال فایل کانفیگ
                await context.bot.send_document(
                    chat_id=user_id,
                    document=config['config'].encode(), 
                    filename=config['filename'],
                    caption=config_caption
                )

                await query.edit_message_text(
                    "✅ کانفیگ با موفقیت ارسال شد.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data='my_services')]])
                )
            except Exception as e:
                logger.error(f"Error sending config: {e}")
                await query.edit_message_text(
                    "❌ خطا در ارسال کانفیگ. لطفا دوباره تلاش کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data='my_services')]])
                )
        else:
            await query.edit_message_text(
                "❌ کانفیگ مورد نظر یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data='my_services')]])
            )

        return USER_ACCOUNT

    elif data == 'support':
        # Get the admin username to use for direct support
        try:
            admin = await context.bot.get_chat(ADMIN_ID)
            admin_username = admin.username if admin.username else None

            if admin_username:
                text = f"💬 برای ارتباط با پشتیبانی، می‌توانید به آیدی زیر پیام دهید:\n\n@{admin_username}\n\nیا پیام خود را همین‌جا ارسال کنید."
            else:
                text = "💬 برای ارتباط با پشتیبانی، لطفا پیام خود را همین‌جا ارسال کنید."

            # Set user in support chat mode
            context.user_data['in_support_chat'] = True

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت", callback_data='exit_support')]
                ])
            )
        except Exception as e:
            logger.error(f"Error getting admin info: {e}")
            await query.edit_message_text(
                "💬 برای ارتباط با پشتیبانی، لطفا پیام خود را ارسال کنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت", callback_data='exit_support')]
                ])
            )
        
        return SUPPORT

    elif data == 'admin_panel':
        # Check admin access properly
        if not is_admin(user_id):
            await query.edit_message_text(
                "⛔ شما دسترسی به پنل مدیریت را ندارید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
            )
            return MAIN_MENU

        await query.edit_message_text(
            "🔧 پنل مدیریت\n\nلطفا یک گزینه را انتخاب کنید:",
            reply_markup=admin_panel_keyboard()
        )
        return ADMIN_PANEL

    elif data.startswith('balance_plan_'):
        try:
            amount = int(data.replace('balance_plan_', ''))
            db = load_database()
            card_number = db['settings'].get('card_number', CARD_NUMBER)
            card_holder = db['settings'].get('card_holder', 'نام و نام خانوادگی')

            # اسکیپ کاراکترهای خاص در فرمت Markdown
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            escaped_card_number = card_number
            escaped_card_holder = card_holder

            for char in special_chars:
                escaped_card_number = escaped_card_number.replace(char, f"\\{char}")
                escaped_card_holder = escaped_card_holder.replace(char, f"\\{char}")

            try:
                await query.edit_message_text(
                    f"💰 افزایش موجودی - {amount} تومان\n\n"
                    f"💳 لطفا مبلغ {amount} تومان را به شماره کارت زیر واریز کنید:\n\n"
                    f"💳 شماره کارت: `{escaped_card_number}`\n"
                    f"👤 به نام: {escaped_card_holder}\n\n"
                    "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]]),
                    parse_mode='MarkdownV2'
                )
            except Exception as e:
                logger.error(f"Error in Markdown formatting: {e}")
                # Fallback to plain text if Markdown fails
                await query.edit_message_text(
                    f"💰 افزایش موجودی - {amount} تومان\n\n"
                    f"💳 لطفا مبلغ {amount} تومان را به شماره کارت زیر واریز کنید:\n\n"
                    f"💳 شماره کارت: {card_number}\n"
                    f"👤 به نام: {card_holder}\n\n"
                    "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]])
                )
                
            context.user_data['payment_amount'] = amount
            return ADD_BALANCE

        except ValueError as e:
            logger.error(f"Error in balance plan: {e}")
            await query.edit_message_text(
                "❌ خطا در انتخاب طرح. لطفا دوباره تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]])
            )
            return ADD_BALANCE

    elif data == 'custom_balance':
        await query.edit_message_text(
            "💰 لطفا مبلغ مورد نظر خود را به تومان وارد کنید:\n"
            "مثال: 75000\n\n"
            "⚠️ فقط عدد وارد کنید، بدون حروف یا علامت های اضافی.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]])
        )
        context.user_data['admin_action'] = 'custom_balance'
        return ADD_BALANCE

    elif data == 'manage_admins':
        if not is_admin(user_id):  # Any admin can manage other admins
            await query.edit_message_text(
                "⛔ شما دسترسی به پنل مدیریت را ندارید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
            )
            return MAIN_MENU

        db = load_database()
        admins = db['settings'].get('admins', [])

        admin_list = ""
        for i, admin_id in enumerate(admins, 1):
            if int(admin_id) != ADMIN_ID:  # Don't show main admin in the list
                admin_list += f"{i}. {admin_id}\n"

        if not admin_list:
            admin_list = "هیچ ادمین اضافی وجود ندارد."

        await query.edit_message_text(
            f"👥 مدیریت ادمین‌ها\n\n"
            f"ادمین اصلی: {ADMIN_ID}\n\n"
            f"سایر ادمین‌ها:\n{admin_list}\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ افزودن ادمین", callback_data='add_admin')],
                [InlineKeyboardButton("➖ حذف ادمین", callback_data='remove_admin')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]
            ])
        )
        return ADMIN_PANEL

    elif data == 'add_admin':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "👥 افزودن ادمین جدید\n\n"
            "لطفا شناسه عددی کاربر مورد نظر را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
        )
        context.user_data['admin_action'] = 'add_new_admin'
        return ADMIN_PANEL

    elif data == 'remove_admin':
        if not is_admin(user_id):
            return MAIN_MENU

        db = load_database()
        admins = db['settings'].get('admins', [])

        # Filter out main admin
        admins_to_remove = [admin_id for admin_id in admins if int(admin_id) != ADMIN_ID]

        if not admins_to_remove:
            await query.edit_message_text(
                "❌ هیچ ادمین اضافی برای حذف وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
            )
            return ADMIN_PANEL

        keyboard = []
        for admin_id in admins_to_remove:
            keyboard.append([InlineKeyboardButton(f"حذف {admin_id}", callback_data=f"del_admin_{admin_id}")])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')])

        await query.edit_message_text(
            "👥 حذف ادمین\n\n"
            "لطفا ادمین مورد نظر برای حذف را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_PANEL
        
    elif data == 'manage_users':
        if not is_admin(user_id):
            return MAIN_MENU
            
        keyboard = [
            [
                InlineKeyboardButton("🚫 مسدود کردن کاربر", callback_data='block_user'),
                InlineKeyboardButton("✅ آزاد کردن کاربر", callback_data='unblock_user')
            ],
            [
                InlineKeyboardButton("📊 دریافت فایل اطلاعات کاربران", callback_data='export_users_data')
            ],
            [
                InlineKeyboardButton("🔎 جستجوی کاربر", callback_data='search_user')
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')
            ]
        ]
        
        await query.edit_message_text(
            "👤 مدیریت کاربران\n\n"
            "لطفا عملیات مورد نظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_PANEL
        
    elif data == 'block_user':
        if not is_admin(user_id):
            return MAIN_MENU
            
        await query.edit_message_text(
            "🚫 مسدود کردن کاربر\n\n"
            "لطفا شناسه کاربر مورد نظر را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
        )
        context.user_data['admin_action'] = 'block_user'
        return ADMIN_PANEL
        
    elif data == 'unblock_user':
        if not is_admin(user_id):
            return MAIN_MENU
            
        # Get list of blocked users
        db = load_database()
        blocked_users = []
        
        for user_id_str, user_data in db['users'].items():
            if user_data.get('is_blocked', False):
                blocked_users.append(user_id_str)
                
        if not blocked_users:
            await query.edit_message_text(
                "⚠️ هیچ کاربر مسدود شده‌ای وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            return ADMIN_PANEL
            
        keyboard = []
        for blocked_user_id in blocked_users:
            keyboard.append([
                InlineKeyboardButton(f"آزاد کردن کاربر {blocked_user_id}", callback_data=f"unblock_user_{blocked_user_id}")
            ])
            
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')])
        
        await query.edit_message_text(
            "✅ آزاد کردن کاربر\n\n"
            "لطفا کاربر مورد نظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_PANEL
        
    elif data.startswith('unblock_user_'):
        if not is_admin(user_id):
            return MAIN_MENU
            
        target_user_id = data.replace('unblock_user_', '')
        
        db = load_database()
        if target_user_id in db['users'] and db['users'][target_user_id].get('is_blocked', False):
            db['users'][target_user_id]['is_blocked'] = False
            save_database(db)
            
            await query.edit_message_text(
                f"✅ کاربر {target_user_id} با موفقیت آزاد شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text="✅ حساب کاربری شما آزاد شد و می‌توانید مجدداً از خدمات ربات استفاده کنید."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {target_user_id}: {e}")
        else:
            await query.edit_message_text(
                "❌ این کاربر یافت نشد یا قبلاً آزاد شده است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
        return ADMIN_PANEL
        
    elif data == 'export_users_data':
        if not is_admin(user_id):
            return MAIN_MENU
            
        try:
            db = load_database()
            users_data = "شناسه کاربر | موجودی | تعداد رفرال‌ها | تعداد کانفیگ‌ها | وضعیت\n"
            users_data += "---------|---------|---------------|---------------|---------\n"
            
            for user_id_str, user_data in db['users'].items():
                balance = user_data.get('balance', 0)
                referrals_count = len(user_data.get('referrals', []))
                configs_count = len(user_data.get('configs', []))
                status = "مسدود" if user_data.get('is_blocked', False) else "فعال"
                
                users_data += f"{user_id_str} | {balance} | {referrals_count} | {configs_count} | {status}\n"
                
            # Create a file with the data
            filename = f"users_data_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(users_data)
                
            # Send the file to admin
            await context.bot.send_document(
                chat_id=user_id,
                document=open(filename, 'rb'),
                caption="📊 اطلاعات کاربران سیستم"
            )
            
            # Remove the file after sending
            os.remove(filename)
            
            await query.edit_message_text(
                "✅ فایل اطلاعات کاربران با موفقیت ارسال شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
        except Exception as e:
            logger.error(f"Error exporting users data: {e}")
            await query.edit_message_text(
                f"❌ خطا در ایجاد فایل اطلاعات: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
        return ADMIN_PANEL
        
    elif data == 'search_user':
        if not is_admin(user_id):
            return MAIN_MENU
            
        await query.edit_message_text(
            "🔎 جستجوی کاربر\n\n"
            "لطفا شناسه کاربر مورد نظر را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
        )
        context.user_data['admin_action'] = 'search_user'
        return ADMIN_PANEL

    elif data.startswith('del_admin_'):
        if not is_admin(user_id):
            return MAIN_MENU

        admin_to_remove = data.replace('del_admin_', '')

        db = load_database()
        if 'admins' in db['settings'] and admin_to_remove in db['settings']['admins']:
            db['settings']['admins'].remove(admin_to_remove)
            save_database(db)

            await query.edit_message_text(
                f"✅ ادمین {admin_to_remove} با موفقیت حذف شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
            )
        else:
            await query.edit_message_text(
                "❌ این ادمین در لیست وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
            )
        return ADMIN_PANEL
        
    elif data.startswith('add_balance_to_'):
        if not is_admin(user_id):
            return MAIN_MENU
            
        target_user_id = data.replace('add_balance_to_', '')
        context.user_data['target_user_id'] = target_user_id
        context.user_data['admin_action'] = 'add_balance_amount'
        
        # Get user current balance
        db = load_database()
        target_user = get_user(int(target_user_id), db)
        
        await query.edit_message_text(
            f"👤 افزایش موجودی کاربر {target_user_id}\n\n"
            f"💰 موجودی فعلی: {target_user['balance']} تومان\n\n"
            f"💸 لطفا مبلغ را همراه با علامت + یا - وارد کنید:\n"
            f"مثال برای افزایش: +50000\n"
            f"مثال برای کاهش: -20000",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
        )
        return ADMIN_PANEL
        
    elif data.startswith('block_user_'):
        if not is_admin(user_id):
            return MAIN_MENU
            
        target_user_id = data.replace('block_user_', '')
        
        # Block user
        db = load_database()
        if target_user_id in db['users']:
            db['users'][target_user_id]['is_blocked'] = True
            save_database(db)
            
            await query.edit_message_text(
                f"✅ کاربر {target_user_id} با موفقیت مسدود شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
            # Notify user about being blocked
            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text="🚫 حساب کاربری شما مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
                )
            except Exception as e:
                logger.error(f"Failed to notify blocked user {target_user_id}: {e}")
        else:
            await query.edit_message_text(
                "❌ کاربر یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
            )
            
        return ADMIN_PANEL

    # Admin panel options
    elif data == 'change_card':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "💳 لطفا انتخاب کنید کدام اطلاعات کارت را می‌خواهید تغییر دهید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔢 تغییر شماره کارت", callback_data='change_card_number')],
                [InlineKeyboardButton("👤 تغییر نام صاحب کارت", callback_data='change_card_holder')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]
            ])
        )
        return ADMIN_PANEL

    elif data == 'change_card_number':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "🔢 لطفا شماره کارت جدید را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
        )
        context.user_data['admin_action'] = 'change_card_number'
        return ADMIN_PANEL

    elif data == 'change_card_holder':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "👤 لطفا نام و نام خانوادگی صاحب کارت را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
        )
        context.user_data['admin_action'] = 'change_card_holder'
        return ADMIN_PANEL

    elif data == 'add_user_balance':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "💰 لطفا شناسه کاربر را وارد کنید:\n"
            "مثال: 123456789",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
        )
        context.user_data['admin_action'] = 'add_user_id'
        return ADMIN_PANEL

    elif data == 'manage_servers':
        if not is_admin(user_id):
            return MAIN_MENU

        await query.edit_message_text(
            "🔄 مدیریت سرورها\n\n"
            "برای فعال یا غیرفعال کردن هر سرور، روی آن کلیک کنید:",
            reply_markup=manage_servers_keyboard()
        )
        return ADMIN_PANEL

    elif data == 'change_server_prices':
        if not is_admin(user_id):
            return MAIN_MENU

        keyboard = []
        for loc_id, loc_info in LOCATIONS.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{loc_info['name']} - {loc_info['price']} تومان", 
                    callback_data=f'edit_price_{loc_id}'
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')])

        await query.edit_message_text(
            "💰 تغییر قیمت سرورها\n\n"
            "برای تغییر قیمت هر سرور، روی آن کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_PANEL

    elif data == 'change_referral_reward':
        if not is_admin(user_id):
            return MAIN_MENU

        db = load_database()
        current_reward = db['settings'].get('referral_reward', DEFAULT_REFERRAL_REWARD)

        await query.edit_message_text(
            f"🔗 تغییر مبلغ پاداش رفرال\n\n"
            f"💰 مبلغ فعلی: {current_reward} تومان\n\n"
            f"💸 لطفا مبلغ جدید را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
        )
        context.user_data['admin_action'] = 'change_referral_reward'
        return ADMIN_PANEL

    # Server management
    elif data.startswith('toggle_server_'):
        if not is_admin(user_id):
            return MAIN_MENU

        server_id = data.replace('toggle_server_', '')
        LOCATIONS[server_id]['active'] = not LOCATIONS[server_id]['active']

        await query.edit_message_text(
            f"🔄 وضعیت سرور {LOCATIONS[server_id]['name']} به "
            f"{'فعال' if LOCATIONS[server_id]['active'] else 'غیرفعال'} تغییر یافت.",
            reply_markup=manage_servers_keyboard()
        )
        return ADMIN_PANEL

    elif data.startswith('edit_price_'):
        if not is_admin(user_id):
            return MAIN_MENU

        location_type = data.replace('edit_price_', '')

        await query.edit_message_text(
            f"💰 تغییر قیمت سرور {LOCATIONS[location_type]['name']}\n\n"
            f"💰 قیمت فعلی: {LOCATIONS[location_type]['price']} تومان\n\n"
            f"💸 لطفا قیمت جدید را به تومان وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='change_server_prices')]])
        )
        context.user_data['admin_action'] = 'change_server_price'
        context.user_data['server_id'] = location_type
        return ADMIN_PANEL

    # Location selection
    elif data.startswith('loc_'):
        location_type = data.replace('loc_', '')
        db = load_database()
        user = get_user(user_id, db)

        if user['balance'] < LOCATIONS[location_type]['price']:
            await query.edit_message_text(
                "⛔ موجودی شما کافی نیست.\n"
                f"قیمت این کانفیگ: {LOCATIONS[location_type]['price']} تومان\n"
                f"موجودی شما: {user['balance']} تومان",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💰 افزایش موجودی", callback_data='add_balance')],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]
                ])
            )
            return MAIN_MENU

        context.user_data['selected_location'] = location_type
        config_preview = generate_wireguard_config(location_type, LOCATIONS)
        context.user_data['config_preview'] = config_preview

        await query.edit_message_text(
            f"🔐 کانفیگ {LOCATIONS[location_type]['name']}\n\n"
            f"💰 قیمت: {LOCATIONS[location_type]['price']} تومان\n"
            f"💳 موجودی شما: {user['balance']} تومان\n"
            f"⏱️ مدت اعتبار: 31 روز\n"
            f"📆 تاریخ انقضا: {config_preview['expiry_date']}\n\n"
            "آیا مایل به خرید این کانفیگ هستید؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله، خرید میکنم", callback_data='confirm_purchase')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_location')]
            ])
        )
        return CONFIG_CONFIRM

    # Payment verification
    elif data.startswith('verify_payment_'):
        if not is_admin(user_id):
            await query.answer("⛔ شما دسترسی به این عملیات را ندارید.", show_alert=True)
            return MAIN_MENU

        # Parse payment info
        try:
            parts = data.split('_')
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                # Handle case where amount might be missing
                amount = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 0

                if amount == 0:
                    # Ask admin to enter the amount if it wasn't included
                    context.user_data['pending_verify_user_id'] = target_user_id
                    await query.edit_message_caption(
                        caption=f"⚠️ مبلغ پرداخت مشخص نشده است.\n"
                              f"لطفا مبلغ پرداخت کاربر {target_user_id} را به تومان وارد کنید:"
                    )
                    context.user_data['admin_action'] = 'enter_payment_amount'
                    return ADMIN_PANEL

                # Update user balance
                db = load_database()
                target_user = get_user(target_user_id, db)

                # Calculate new balance
                old_balance = target_user['balance']
                target_user['balance'] += amount
                new_balance = target_user['balance']

                save_database(db)

                # Notify admin
                await query.edit_message_caption(
                    caption=f"✅ پرداخت کاربر {target_user_id} به مبلغ {amount} تومان تایید شد.\n"
                          f"💰 موجودی قبلی: {old_balance} تومان\n"
                          f"💰 موجودی جدید: {new_balance} تومان"
                )

                # Notify user
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ پرداخت شما به مبلغ {amount} تومان تایید شد.\n\n"
                         f"💰 موجودی قبلی: {old_balance} تومان\n"
                         f"💰 موجودی جدید: {new_balance} تومان\n\n"
                         f"با تشکر از شما"
                )
            else:
                raise ValueError("Invalid payment data format")

        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            await query.answer("❌ خطا در پردازش پرداخت.", show_alert=True)

        return ADMIN_PANEL

    elif data.startswith('reject_payment_'):
        if not is_admin(user_id):
            await query.answer("⛔ شما دسترسی به این عملیات را ندارید.", show_alert=True)
            return MAIN_MENU

        # Parse user ID
        try:
            _, target_user_id = data.split('_', 1)
            target_user_id = int(target_user_id)

            # Notify admin
            await query.edit_message_caption(
                caption=f"❌ پرداخت کاربر {target_user_id} رد شد."
            )

            # Notify user
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ متأسفانه پرداخت شما تایید نشد.\n\n"
                     "دلایل احتمالی:\n"
                     "- تصویر رسید ناخوانا بود\n"
                     "- مبلغ واریزی مطابقت نداشت\n"
                     "- اطلاعات پرداخت ناقص بود\n\n"
                     "لطفا دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
            )

        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")
            await query.answer("❌ خطا در پردازش رد پرداخت.", show_alert=True)

        return ADMIN_PANEL

    # Purchase confirmation
    elif data == 'confirm_purchase':
        try:
            location_type = context.user_data.get('selected_location')
            config_data = context.user_data.get('config_preview')

            if not location_type or not config_data:
                await query.edit_message_text(
                    "❌ خطا در فرآیند خرید. لطفا دوباره تلاش کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
                )
                return MAIN_MENU

            db = load_database()
            user = get_user(user_id, db)

            # Check balance again to prevent any issues
            if user['balance'] < LOCATIONS[location_type]['price']:
                await query.edit_message_text(
                    "⛔ موجودی شما کافی نیست.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
                )
                return MAIN_MENU

            # Deduct balance
            old_balance = user['balance']
            user['balance'] -= LOCATIONS[location_type]['price']

            # Save config
            config_id = str(uuid.uuid4())
            db['configs'][config_id] = config_data
            user['configs'].append(config_id)

            save_database(db)

            # Get caption for the config file
            config_caption = get_config_caption(config_data, location_type)

            try:
                # Send config as a text file
                await context.bot.send_document(
                    chat_id=user_id,
                    document=config_data['config'].encode(), 
                    filename=config_data['filename'],
                    caption=config_caption,
                    parse_mode='MarkdownV2'
                )
            except Exception as e:
                logger.error(f"Error sending config with MarkdownV2: {e}")
                # Fallback without markdown formatting
                await context.bot.send_document(
                    chat_id=user_id,
                    document=config_data['config'].encode(), 
                    filename=config_data['filename'],
                    caption=f"کانفیگ {config_data['name']} - تاریخ انقضا: {config_data['expiry_date']}"
                )

            # Notify user about the balance change
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💰 کاهش موجودی\n\n"
                     f"✅ مبلغ {LOCATIONS[location_type]['price']} تومان بابت خرید کانفیگ {LOCATIONS[location_type]['name']} از حساب شما کسر شد.\n"
                     f"💳 موجودی قبلی: {old_balance} تومان\n"
                     f"💳 موجودی فعلی: {user['balance']} تومان"
            )

            await query.edit_message_text(
                "✅ خرید شما با موفقیت انجام شد. کانفیگ به صورت فایل برای شما ارسال شد.\n\n"
                f"⏱️ اعتبار: 31 روز\n"
                f"💰 موجودی باقیمانده: {user['balance']} تومان",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='back_to_main')]])
            )

            # Clear user_data to prevent issues with future purchases
            if 'selected_location' in context.user_data:
                del context.user_data['selected_location']
            if 'config_preview' in context.user_data:
                del context.user_data['config_preview']

            return MAIN_MENU

        except Exception as e:
            logger.error(f"Error in purchase process: {e}")
            await query.edit_message_text(
                "❌ خطایی در فرآیند خرید رخ داد. لطفا دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
            )
            return MAIN_MENU

    # Support chat controls
    elif data == 'exit_support':
        # Exit support chat mode
        if 'in_support_chat' in context.user_data:
            del context.user_data['in_support_chat']
        
        await query.edit_message_text(
            "🏠 منوی اصلی\n\nلطفا یک گزینه را انتخاب کنید:",
            reply_markup=main_menu_keyboard(user_id)
        )
        return MAIN_MENU
        
    elif data == 'continue_support':
        # Stay in support chat mode
        await query.edit_message_text(
            "💬 لطفا پیام جدید خود را برای پشتیبانی ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='exit_support')]])
        )
        return SUPPORT
        
    elif data.startswith('reply_to_user_'):
        if not is_admin(user_id):
            return MAIN_MENU
            
        target_user_id = int(data.replace('reply_to_user_', ''))
        context.user_data['admin_action'] = 'reply_to_user'
        context.user_data['reply_to_user_id'] = target_user_id
        
        await query.edit_message_text(
            f"📤 در حال پاسخ به کاربر {target_user_id}\n\n"
            "لطفا پاسخ خود را بنویسید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 لغو", callback_data='back_to_admin')]])
        )
        
        return ADMIN_PANEL
    
    # Navigation
    elif data == 'back_to_main':
        # Also clear support chat mode if exists
        if 'in_support_chat' in context.user_data:
            del context.user_data['in_support_chat']
            
        await query.edit_message_text(
            "🏠 منوی اصلی\n\nلطفا یک گزینه را انتخاب کنید:",
            reply_markup=main_menu_keyboard(user_id)
        )
        return MAIN_MENU

    elif data == 'back_to_admin':
        await query.edit_message_text(
            "🔧 پنل مدیریت\n\nلطفا یک گزینه را انتخاب کنید:",
            reply_markup=admin_panel_keyboard()
        )
        return ADMIN_PANEL

    elif data == 'back_to_location':
        await query.edit_message_text(
            "لطفا نوع لوکیشن مورد نظر خود را انتخاب کنید:",
            reply_markup=location_keyboard()
        )
        return LOCATION_SELECT

    return MAIN_MENU

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Handle admin actions
    if (is_admin(user_id) or user_id == ADMIN_ID) and 'admin_action' in context.user_data:
        action = context.user_data['admin_action']

        if action == 'change_card_number':
            # Update card number
            db = load_database()
            db['settings']['card_number'] = text.strip()
            save_database(db)

            await update.message.reply_text(
                f"✅ شماره کارت با موفقیت به {text.strip()} تغییر یافت.",
                reply_markup=admin_panel_keyboard()
            )
            del context.user_data['admin_action']
            return ADMIN_PANEL

        elif action == 'change_card_holder':
            # Update card holder name
            db = load_database()
            db['settings']['card_holder'] = text.strip()
            save_database(db)

            await update.message.reply_text(
                f"✅ نام صاحب کارت با موفقیت به {text.strip()} تغییر یافت.",
                reply_markup=admin_panel_keyboard()
            )
            del context.user_data['admin_action']
            return ADMIN_PANEL

        elif action == 'change_server_price':
            try:
                new_price = int(text.strip())
                server_id = context.user_data.get('server_id')

                if not server_id or server_id not in LOCATIONS:
                    raise ValueError("سرور نامعتبر است")

                if new_price < 0:
                    raise ValueError("قیمت نمی‌تواند منفی باشد")

                # Update the price
                LOCATIONS[server_id]['price'] = new_price

                # Save to file (we would need to update ranges.py in a real scenario)
                # For simplicity, we're just updating the in-memory version here

                await update.message.reply_text(
                    f"✅ قیمت سرور {LOCATIONS[server_id]['name']} با موفقیت به {new_price} تومان تغییر یافت.",
                    reply_markup=admin_panel_keyboard()
                )

                # Clear user data
                if 'admin_action' in context.user_data:
                    del context.user_data['admin_action']
                if 'server_id' in context.user_data:
                    del context.user_data['server_id']

                return ADMIN_PANEL

            except ValueError as e:
                await update.message.reply_text(
                    f"❌ خطا: {str(e) if 'سرور' in str(e) or 'قیمت' in str(e) else 'لطفا یک عدد صحیح وارد کنید.'}\n",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='change_server_prices')]])
                )
                return ADMIN_PANEL

        elif action == 'change_referral_reward':
            try:
                new_reward = int(text.strip())

                if new_reward < 0:
                    raise ValueError("مبلغ پاداش نمی‌تواند منفی باشد")

                # Update the referral reward
                db = load_database()
                db['settings']['referral_reward'] = new_reward
                save_database(db)

                await update.message.reply_text(
                    f"✅ مبلغ پاداش رفرال با موفقیت به {new_reward} تومان تغییر یافت.",
                    reply_markup=admin_panel_keyboard()
                )

                del context.user_data['admin_action']
                return ADMIN_PANEL

            except ValueError as e:
                await update.message.reply_text(
                    f"❌ خطا: {str(e) if 'مبلغ' in str(e) else 'لطفا یک عدد صحیح وارد کنید.'}\n",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='change_referral_reward')]])
                )
                return ADMIN_PANEL

        elif action == 'add_user_id':
            try:
                target_user_id = int(text.strip())

                # Check if user exists or create them
                db = load_database()
                target_user = get_user(target_user_id, db)

                # Store the target user ID for the next step
                context.user_data['target_user_id'] = target_user_id
                context.user_data['admin_action'] = 'add_balance_amount'

                await update.message.reply_text(
                    f"👤 اطلاعات کاربر:\n"
                    f"🪪 شناسه: {target_user_id}\n"
                    f"💰 موجودی فعلی: {target_user['balance']} تومان\n\n"
                    f"💸 لطفا مبلغ را همراه با علامت + یا - وارد کنید:\n"
                    f"مثال برای افزایش: +50000\n"
                    f"مثال برای کاهش: -20000",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
                )
                return ADMIN_PANEL

            except ValueError:
                await update.message.reply_text(
                    "❌ فرمت وارد شده صحیح نیست.\n"
                    "لطفا یک شناسه کاربری معتبر (عدد) وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
                )
                return ADMIN_PANEL

        elif action == 'add_balance_amount':
            try:
                amount_text = text.strip()

                # Check if the input starts with + or -
                if not (amount_text.startswith('+') or amount_text.startswith('-')):
                    raise ValueError("باید با + یا - شروع شود")

                # Parse the amount
                amount = int(amount_text)
                target_user_id = context.user_data.get('target_user_id')

                if not target_user_id:
                    raise ValueError("شناسه کاربر یافت نشد")

                # Update user balance
                db = load_database()
                target_user = get_user(target_user_id, db)

                # Calculate new balance
                old_balance = target_user['balance']
                target_user['balance'] += amount
                new_balance = target_user['balance']

                # Prevent negative balance
                if new_balance < 0:
                    await update.message.reply_text(
                        "❌ موجودی کاربر نمی‌تواند منفی شود.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
                    )
                    return ADMIN_PANEL

                save_database(db)

                # Create appropriate message based on increase or decrease
                if amount > 0:
                    admin_message = f"✅ مبلغ {abs(amount)} تومان به موجودی کاربر {target_user_id} اضافه شد."
                    user_message = f"💰 موجودی حساب شما به میزان {abs(amount)} تومان افزایش یافت."
                else:
                    admin_message = f"✅ مبلغ {abs(amount)} تومان از موجودی کاربر {target_user_id} کم شد."
                    user_message = f"💰 موجودی حساب شما به میزان {abs(amount)} تومان کاهش یافت."

                await update.message.reply_text(
                    f"{admin_message}\n"
                    f"💰 موجودی قبلی: {old_balance} تومان\n"
                    f"💰 موجودی جدید: {new_balance} تومان",
                    reply_markup=admin_panel_keyboard()
                )

                # Notify user of balance change
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"{user_message}\n"
                             f"💰 موجودی فعلی: {new_balance} تومان"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {target_user_id}: {e}")

                # Clear user data
                if 'admin_action' in context.user_data:
                    del context.user_data['admin_action']
                if 'target_user_id' in context.user_data:
                    del context.user_data['target_user_id']

                return ADMIN_PANEL

            except ValueError as e:
                await update.message.reply_text(
                    f"❌ خطا: {str(e) if 'باید' in str(e) or 'شناسه' in str(e) else 'لطفا یک عدد صحیح با علامت + یا - وارد کنید.'}\n",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_admin')]])
                )
                return ADMIN_PANEL

        elif action == 'custom_balance':
            try:
                amount = int(text.strip())

                if amount <= 0:
                    raise ValueError("مبلغ باید بزرگتر از صفر باشد")

                db = load_database()
                card_number = db['settings']['card_number']
                card_holder = db['settings'].get('card_holder', 'نام و نام خانوادگی')

                # اسکیپ کاراکترهای خاص در فرمت Markdown
                # Process special characters for MarkdownV2 format
                special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                escaped_card_number = card_number
                escaped_card_holder = card_holder

                for char in special_chars:
                    escaped_card_number = escaped_card_number.replace(char, f"\\{char}")
                    escaped_card_holder = escaped_card_holder.replace(char, f"\\{char}")

                try:
                    await update.message.reply_text(
                        f"💰 افزایش موجودی - {amount} تومان\n\n"
                        f"💳 لطفا مبلغ {amount} تومان را به شماره کارت زیر واریز کنید:\n\n"
                        f"💳 شماره کارت: `{escaped_card_number}`\n"
                        f"👤 به نام: {escaped_card_holder}\n\n"
                        "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]]),
                        parse_mode='MarkdownV2'
                    )
                except Exception as e:
                    logger.error(f"Error in sending Markdown formatted message: {e}")
                    # Fallback to plain text if Markdown fails
                    await update.message.reply_text(
                        f"💰 افزایش موجودی - {amount} تومان\n\n"
                        f"💳 لطفا مبلغ {amount} تومان را به شماره کارت زیر واریز کنید:\n\n"
                        f"💳 شماره کارت: {card_number}\n"
                        f"👤 به نام: {card_holder}\n\n"
                        "📸 پس از واریز، لطفا تصویر رسید پرداخت را ارسال کنید.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]])
                    )

                context.user_data['payment_amount'] = amount
                del context.user_data['admin_action']
                return ADD_BALANCE

            except ValueError as e:
                await update.message.reply_text(
                    f"❌ خطا: {str(e) if 'مبلغ' in str(e) else 'لطفا یک عدد صحیح مثبت وارد کنید.'}\n",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='add_balance')]])
                )
                return ADD_BALANCE

        elif action == 'enter_payment_amount':
            try:
                amount = int(text.strip())
                target_user_id = context.user_data.get('pending_verify_user_id')

                if not target_user_id:
                    raise ValueError("شناسه کاربر یافت نشد")

                if amount <= 0:
                    raise ValueError("مبلغ باید بزرگتر از صفر باشد")

                # Update user balance
                db = load_database()
                target_user = get_user(target_user_id, db)

                # Calculate new balance
                old_balance = target_user['balance']
                target_user['balance'] += amount
                new_balance = target_user['balance']

                save_database(db)

                await update.message.reply_text(
                    f"✅ پرداخت کاربر {target_user_id} به مبلغ {amount} تومان تایید شد.\n"
                    f"💰 موجودی قبلی: {old_balance} تومان\n"
                    f"💰 موجودی جدید: {new_balance} تومان",
                    reply_markup=admin_panel_keyboard()
                )

                # Notify user of balance change
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"✅ پرداخت شما به مبلغ {amount} تومان تایید شد.\n\n"
                             f"💰 موجودی قبلی: {old_balance} تومان\n"
                             f"💰 موجودی جدید: {new_balance} تومان\n\n"
                             f"با تشکر از شما"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {target_user_id}: {e}")

                # Clear user data
                if 'admin_action' in context.user_data:
                    del context.user_data['admin_action']
                if 'pending_verify_user_id' in context.user_data:
                    del context.user_data['pending_verify_user_id']

                return ADMIN_PANEL

            except ValueError as e:
                await update.message.reply_text(
                    f"❌ خطا: {str(e) if 'مبلغ' in str(e) or 'شناسه' in str(e) else 'لطفا یک عدد صحیح مثبت وارد کنید.'}\n",
                    reply_markup=admin_panel_keyboard()
                )
                return ADMIN_PANEL

        elif action == 'add_new_admin':
            if not is_admin(user_id):  # Any admin can add other admins
                return MAIN_MENU

            try:
                new_admin_id = int(text.strip())

                db = load_database()
                if 'admins' not in db['settings']:
                    db['settings']['admins'] = []

                # Check if already an admin
                if str(new_admin_id) in db['settings']['admins'] or new_admin_id == ADMIN_ID:
                    await update.message.reply_text(
                        "❌ این کاربر قبلاً ادمین است.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
                    )
                else:
                    db['settings']['admins'].append(str(new_admin_id))

                    # تنظیم موجودی ادمین جدید به 1 میلیارد تومان
                    admin_user = get_user(new_admin_id, db)
                    admin_user['balance'] = 1000000000  # 1 میلیارد تومان
                    save_database(db)

                    await update.message.reply_text(
                        f"✅ کاربر {new_admin_id} با موفقیت به عنوان ادمین اضافه شد.\n"
                        f"💰 موجودی این ادمین به 1 میلیارد تومان تنظیم شد.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
                    )

                del context.user_data['admin_action']
                return ADMIN_PANEL

            except ValueError:
                await update.message.reply_text(
                    "❌ فرمت وارد شده صحیح نیست.\n"
                    "لطفا یک شناسه کاربری معتبر (عدد) وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_admins')]])
                )
                return ADMIN_PANEL
                
        elif action == 'block_user':
            if not is_admin(user_id):
                return MAIN_MENU
                
            try:
                target_user_id = int(text.strip())
                
                # Check if user exists
                db = load_database()
                target_user = get_user(target_user_id, db)
                
                # Check if user is already blocked
                if target_user.get('is_blocked', False):
                    await update.message.reply_text(
                        f"⚠️ کاربر {target_user_id} قبلاً مسدود شده است.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
                    )
                    del context.user_data['admin_action']
                    return ADMIN_PANEL
                
                # Block user
                target_user['is_blocked'] = True
                save_database(db)
                
                await update.message.reply_text(
                    f"✅ کاربر {target_user_id} با موفقیت مسدود شد.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
                )
                
                # Notify user about being blocked
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="🚫 حساب کاربری شما مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify blocked user {target_user_id}: {e}")
                
                del context.user_data['admin_action']
                return ADMIN_PANEL
                
            except ValueError:
                await update.message.reply_text(
                    "❌ فرمت وارد شده صحیح نیست.\n"
                    "لطفا یک شناسه کاربری معتبر (عدد) وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
                )
                return ADMIN_PANEL
                
        elif action == 'search_user':
            if not is_admin(user_id):
                return MAIN_MENU
                
            try:
                target_user_id = int(text.strip())
                target_user_id_str = str(target_user_id)
                
                # Get user data
                db = load_database()
                
                if target_user_id_str in db['users']:
                    user_data = db['users'][target_user_id_str]
                    
                    balance = user_data.get('balance', 0)
                    referrals_count = len(user_data.get('referrals', []))
                    configs_count = len(user_data.get('configs', []))
                    status = "مسدود" if user_data.get('is_blocked', False) else "فعال"
                    
                    # Create buttons for actions on this user
                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "🚫 مسدود کردن" if not user_data.get('is_blocked', False) else "✅ آزاد کردن", 
                                callback_data=f"{'block_user' if not user_data.get('is_blocked', False) else 'unblock_user'}_{target_user_id_str}"
                            )
                        ],
                        [
                            InlineKeyboardButton("💰 افزایش موجودی", callback_data=f"add_balance_to_{target_user_id_str}")
                        ],
                        [
                            InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')
                        ]
                    ]
                    
                    await update.message.reply_text(
                        f"🔎 اطلاعات کاربر {target_user_id}\n\n"
                        f"💰 موجودی: {balance} تومان\n"
                        f"👥 تعداد رفرال‌ها: {referrals_count}\n"
                        f"🔐 تعداد کانفیگ‌ها: {configs_count}\n"
                        f"⚙️ وضعیت: {status}\n\n"
                        f"لطفا عملیات مورد نظر را انتخاب کنید:",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await update.message.reply_text(
                        f"❌ کاربری با شناسه {target_user_id} یافت نشد.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
                    )
                
                del context.user_data['admin_action']
                return ADMIN_PANEL
                
            except ValueError:
                await update.message.reply_text(
                    "❌ فرمت وارد شده صحیح نیست.\n"
                    "لطفا یک شناسه کاربری معتبر (عدد) وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_users')]])
                )
                return ADMIN_PANEL

        elif action == 'reply_to_user':
            # Admin is replying to a user's support message
            try:
                target_user_id = context.user_data.get('reply_to_user_id')
                
                if not target_user_id:
                    await update.message.reply_text(
                        "❌ خطا: شناسه کاربر برای پاسخ یافت نشد.",
                        reply_markup=admin_panel_keyboard()
                    )
                    del context.user_data['admin_action']
                    return ADMIN_PANEL
                
                # Send reply to user
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📞 پاسخ پشتیبانی:\n\n{text}"
                )
                
                await update.message.reply_text(
                    f"✅ پاسخ شما به کاربر {target_user_id} ارسال شد.",
                    reply_markup=admin_panel_keyboard()
                )
                
                # Clear user data
                if 'admin_action' in context.user_data:
                    del context.user_data['admin_action']
                if 'reply_to_user_id' in context.user_data:
                    del context.user_data['reply_to_user_id']
                
                return ADMIN_PANEL
                
            except Exception as e:
                logger.error(f"Error in replying to user: {e}")
                await update.message.reply_text(
                    f"❌ خطا در ارسال پاسخ: {e}",
                    reply_markup=admin_panel_keyboard()
                )
                return ADMIN_PANEL

    # Handle support messages from users
    if update.message.chat.type == 'private' and context.user_data.get('in_support_chat', False):
        # User is in support chat mode
        if user_id != ADMIN_ID:
            try:
                # Forward to main admin
                forwarded_msg = await context.bot.forward_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=update.message.chat_id,
                    message_id=update.message.message_id
                )
                
                # Add reply button for admin
                reply_keyboard = [
                    [InlineKeyboardButton("📤 پاسخ به کاربر", callback_data=f"reply_to_user_{user_id}")]
                ]
                
                # Store user ID for context
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"👤 شناسه کاربر: {user_id}",
                    reply_to_message_id=forwarded_msg.message_id,
                    reply_markup=InlineKeyboardMarkup(reply_keyboard)
                )
                
                # Also forward to other admins
                db = load_database()
                if 'admins' in db['settings']:
                    for admin_id in db['settings']['admins']:
                        if str(admin_id) != str(ADMIN_ID):  # Skip main admin
                            try:
                                forwarded_to_other = await context.bot.forward_message(
                                    chat_id=int(admin_id),
                                    from_chat_id=update.message.chat_id,
                                    message_id=update.message.message_id
                                )
                                
                                # Add reply button for other admins
                                await context.bot.send_message(
                                    chat_id=int(admin_id),
                                    text=f"👤 شناسه کاربر: {user_id}",
                                    reply_to_message_id=forwarded_to_other.message_id,
                                    reply_markup=InlineKeyboardMarkup(reply_keyboard)
                                )
                            except Exception as e:
                                logger.error(f"Failed to forward to admin {admin_id}: {e}")

                # Confirm message received
                await update.message.reply_text(
                    "✅ پیام شما به پشتیبانی ارسال شد. در اسرع وقت پاسخ داده خواهد شد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📤 ارسال پیام دیگر", callback_data="continue_support")],
                        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="exit_support")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to forward message to admin: {e}")
                await update.message.reply_text(
                    "❌ خطا در ارسال پیام به پشتیبانی. لطفا بعدا دوباره تلاش کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="exit_support")]])
                )
        else:
            # Admin replying to a forwarded message
            is_reply = update.message.reply_to_message is not None
            
            # Check for user ID mention in the previous message
            user_id_to_reply = None
            
            if is_reply:
                if update.message.reply_to_message.forward_from:
                    # Traditional way - only works if user hasn't restricted forwards
                    user_id_to_reply = update.message.reply_to_message.forward_from.id
                elif update.message.reply_to_message.text and "شناسه کاربر:" in update.message.reply_to_message.text:
                    # Extract from our custom message
                    try:
                        user_id_text = update.message.reply_to_message.text.split("شناسه کاربر:")[1].strip()
                        user_id_to_reply = int(user_id_text)
                    except Exception as e:
                        logger.error(f"Failed to extract user ID from text: {e}")
                        
                # Check previous message for ID if nothing found yet
                if not user_id_to_reply and update.message.reply_to_message.reply_to_message:
                    prev_msg = update.message.reply_to_message.reply_to_message
                    if prev_msg.forward_from:
                        user_id_to_reply = prev_msg.forward_from.id
            
            if user_id_to_reply:
                try:
                    await context.bot.send_message(
                        chat_id=user_id_to_reply,
                        text=f"📞 پاسخ پشتیبانی:\n\n{text}"
                    )

                    await update.message.reply_text(
                        f"✅ پاسخ شما به کاربر {user_id_to_reply} ارسال شد.",
                        reply_markup=admin_panel_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Failed to send admin reply to user {user_id_to_reply}: {e}")
                    await update.message.reply_text(
                        f"❌ خطا در ارسال پاسخ: {e}",
                        reply_markup=admin_panel_keyboard()
                    )
            elif is_reply:
                # The admin replied to a message but we couldn't extract user ID
                await update.message.reply_text(
                    "⚠️ نمی‌توان شناسه کاربر را از این پیام استخراج کرد.\n"
                    "لطفا از دکمه «پاسخ به کاربر» استفاده کنید یا به پیامی پاسخ دهید که شناسه کاربر را نمایش می‌دهد.",
                    reply_markup=admin_panel_keyboard()
                )
    elif update.message.chat.type == 'private' and data.get('admin_action') != 'reply_to_user':
        # This is a regular user message (not in support chat)
        # Redirect user to start command or support section
        if user_id != ADMIN_ID:  # Skip for admin
            await update.message.reply_text(
                "برای استفاده از ربات لطفا از منوی زیر گزینه مورد نظر خود را انتخاب کنید.",
                reply_markup=main_menu_keyboard(user_id)
            )

    return MAIN_MENU

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Get payment amount if available
    payment_amount = context.user_data.get('payment_amount', None)
    amount_text = f"به مبلغ {payment_amount} تومان" if payment_amount else ""

    # Get file ID of the photo
    photo_file_id = update.message.photo[-1].file_id

    # Get caption from the photo if available
    photo_caption = update.message.caption or ""

    # Create a proper callback data string - ensure payment_amount is included
    verify_callback = f"verify_payment_{user_id}"
    if payment_amount:
        verify_callback += f"_{payment_amount}"
    else:
        # If payment amount is not provided, create a callback that will prompt for amount
        verify_callback = f"verify_payment_{user_id}_0"

    # Add receipt verification options for admin
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ تایید پرداخت", callback_data=verify_callback),
            InlineKeyboardButton("❌ رد پرداخت", callback_data=f"reject_payment_{user_id}")
        ]
    ]

    # Handle payment receipt - Acknowledge receipt to user
    await update.message.reply_text(
        f"🧾 رسید پرداخت شما {amount_text} دریافت شد و در حال بررسی است.\n"
        "پس از تایید، موجودی شما افزایش خواهد یافت.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='back_to_main')]])
    )

    # Forward to admin for verification
    try:
        # Combine user caption with system info
        full_caption = f"🧾 رسید پرداخت از کاربر {user_id}\n"
        full_caption += f"💰 مبلغ: {payment_amount if payment_amount else 'نامشخص'} تومان\n"

        # Add user caption if it exists
        if photo_caption:
            full_caption += f"\n💬 توضیحات کاربر: {photo_caption}\n"

        full_caption += "\nلطفا پرداخت را تایید یا رد کنید:"

        # Send photo to admin with verification buttons
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file_id,
            caption=full_caption,
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
        )

        # Also notify any other admins
        db = load_database()
        if 'admins' in db['settings']:
            for admin_id in db['settings']['admins']:
                if int(admin_id) != ADMIN_ID:  # Don't send duplicate to main admin
                    try:
                        await context.bot.send_photo(
                            chat_id=int(admin_id),
                            photo=photo_file_id,
                            caption=f"🧾 رسید پرداخت از کاربر {user_id}\n"
                                    f"💰 مبلغ: {payment_amount if payment_amount else 'نامشخص'} تومان\n"
                                    f"\n💬 این پیام فقط برای اطلاع شماست. تایید یا رد توسط ادمین اصلی انجام می‌شود.",
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id}: {e}")

        # Store payment details in database for later verification
        if 'pending_payments' not in db:
            db['pending_payments'] = {}

        db['pending_payments'][f"{user_id}_{int(datetime.now().timestamp())}"] = {
            'user_id': user_id,
            'amount': payment_amount,
            'timestamp': datetime.now().isoformat(),
            'status': 'pending',
            'caption': photo_caption
        }
        save_database(db)

        # Clear payment amount from context after storing in DB
        if 'payment_amount' in context.user_data:
            del context.user_data['payment_amount']

    except Exception as e:
        logger.error(f"Failed to forward payment receipt to admin: {e}")
        # Notify user about error
        await update.message.reply_text(
            "❌ خطایی در ارسال رسید به ادمین رخ داد. لطفا دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
        )

    return MAIN_MENU

def main():
    # Initialize database
    db = init_database()

    # Make sure settings has admins list
    if 'admins' not in db['settings']:
        db['settings']['admins'] = [ADMIN_ID]
        save_database(db)

    # تنظیم موجودی ادمین اصلی
    admin_user = get_user(ADMIN_ID, db)
    if admin_user['balance'] == 0:
        admin_user['balance'] = 1000000000  # 1 میلیارد تومان
        save_database(db)
        logger.info(f"Admin balance updated to 1000000000")

    # Create application
    application = Application.builder().token(TOKEN).build()

    # Log successful startup
    print("bot start successfully✅")
    logger.info("bot start successfully✅")

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(button_handler)
            ],
            ADMIN_PANEL: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
            ],
            ADD_BALANCE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.PHOTO, photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
            ],
            LOCATION_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            CONFIG_CONFIRM: [
                CallbackQueryHandler(button_handler)
            ],
            SUPPORT: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
            ],
            USER_ACCOUNT: [
                CallbackQueryHandler(button_handler)
            ],
            REFERRAL: [
                CallbackQueryHandler(button_handler)
            ],
            ABOUT_US: [
                CallbackQueryHandler(button_handler)
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)

    # Start the bot in polling mode
    print("Running in polling mode")
    
    # Use the non-awaitable method to run the bot (handles the event loop internally)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()