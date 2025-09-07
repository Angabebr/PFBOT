import logging
import asyncio
import requests
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1040886421  
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
cancel_button = KeyboardButton(text="Отмена")
cancel_kb = ReplyKeyboardMarkup(keyboard=[[cancel_button]], resize_keyboard=True, one_time_keyboard=True)
# Главное меню
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="FAQ"), KeyboardButton(text="Калькулятор доставки")],
        [KeyboardButton(text="Создать тикет"), KeyboardButton(text="Контакты администратора")]
    ],
    resize_keyboard=True
)

# Получение курсов валют

def get_yuan_exchange_rate():
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js")
        data = response.json()
        yuan_rate = data['Valute']['CNY']['Value']
        return yuan_rate + 1.3
    except Exception as e:
        logging.error(f"Ошибка получения курса юаня: {e}")
        return 13.8

def get_euro_exchange_rate():
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js")
        data = response.json()
        euro_rate = data['Valute']['EUR']['Value']
        return euro_rate
    except Exception as e:
        logging.error(f"Ошибка получения курса евро: {e}")
        return 100.0

@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать в магазин! Выберите нужный раздел:", reply_markup=menu_keyboard)

# FAQ
faq_data = {
    "доставка": "Мы доставляем по всей стране в течение 10-21 дней.",
    "оплата": "Доступны оплаты: карта, перевод, наложенный платёж."
}

@dp.message(F.text == "FAQ")
async def show_faq(message: types.Message):
    text = "Часто задаваемые вопросы:\n\n"
    for key, value in faq_data.items():
        text += f"• {key.capitalize()}: {value}\n"
    await message.answer(text)

@dp.message(F.text=="Контакты администратора")
async def contact_admin(message: types.Message):
    await message.answer("Свяжитесь с администратором: @demigodez")
    
# Калькулятор доставки
class DeliveryCalc(StatesGroup):
    waiting_for_price = State()
    waiting_for_weight = State()
    waiting_for_method = State()
    waiting_for_insurance = State()

@dp.message(F.text == "Калькулятор доставки")
async def start_calc(message: types.Message, state: FSMContext):
    await message.answer("Введите цену товара в юанях:", reply_markup=cancel_kb)
    await state.set_state(DeliveryCalc.waiting_for_price)

@dp.message(DeliveryCalc.waiting_for_price)
async def get_price(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return
    try:
        price = float(message.text)
        yuan = get_yuan_exchange_rate()
        rub = price * yuan
        await state.update_data(price_rub=rub)
        await message.answer(f"Курс юаня: {round(yuan, 2)} ₽. Введите вес посылки в кг:", reply_markup=cancel_kb)
        await state.set_state(DeliveryCalc.waiting_for_weight)
    except ValueError:
        await message.answer("Введите числовое значение.", reply_markup=cancel_kb)

@dp.message(DeliveryCalc.waiting_for_weight)
async def get_weight(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return
    try:
        weight = float(message.text)
        cost = weight * 640
        await state.update_data(shipping_cost=cost)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="СДЭК"), KeyboardButton(text="Почта РФ")]],
            resize_keyboard=True
        )
        await message.answer("Выберите метод доставки:", reply_markup=kb)
        await state.set_state(DeliveryCalc.waiting_for_method)
    except ValueError:
        await message.answer("Введите вес числом.", reply_markup=cancel_kb)

@dp.message(DeliveryCalc.waiting_for_method)
async def get_method(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    method = message.text
    if method not in ["СДЭК", "Почта РФ"]:
        await message.answer("Выберите СДЭК или Почта РФ", reply_markup=cancel_kb)
        return

    data = await state.get_data()
    total = data["price_rub"] + data["shipping_cost"]
    total *= 1.15 if method == "СДЭК" else 1.10
    await state.update_data(total=total)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True
    )
    await message.answer("Хотите добавить защиту от рисков за 100 ₽?", reply_markup=kb)
    await state.set_state(DeliveryCalc.waiting_for_insurance)

@dp.message(DeliveryCalc.waiting_for_insurance)
async def get_insurance(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    response = message.text.lower()
    data = await state.get_data()
    total = data["total"]

    if response == "да":
        total += 100
    elif response != "нет":
        await message.answer("Выберите Да или Нет", reply_markup=cancel_kb)
        return

    euro = get_euro_exchange_rate()
    threshold = euro * 200
    if total > threshold:
        duty = total * 0.05
        total += duty
        await message.answer(f"Таможенная пошлина: {round(duty, 2)} ₽")

    await message.answer(f"Итоговая стоимость: {round(total, 2)} ₽", reply_markup=menu_keyboard)
    await state.clear()

# Тикет-система
class Ticket(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_method = State()
    waiting_for_address = State()

@dp.message(F.text == "Создать тикет")
async def ticket_start(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото товара:", reply_markup=cancel_kb)  # добавил отмену
    await state.set_state(Ticket.waiting_for_photo)

@dp.message(Ticket.waiting_for_photo, F.content_type == ContentType.PHOTO)
async def ticket_photo(message: types.Message, state: FSMContext):
    if message.text == "Отмена":  # на всякий случай, если прилетит текст
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    try:
        file_id = message.photo[-1].file_id
        await state.update_data(photo=file_id)
        await message.answer("Введите ФИО и телеграмм юз:", reply_markup=cancel_kb)
        await state.set_state(Ticket.waiting_for_name)
    except Exception as e:
        logging.error(f"Ошибка фото: {e}")
        await message.answer("Ошибка при обработке фото. Попробуйте снова.")

@dp.message(Ticket.waiting_for_photo)
async def ticket_photo_invalid(message: types.Message):
    if message.text == "Отмена":
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return
    await message.answer("Пожалуйста, отправьте именно фото.", reply_markup=cancel_kb)

@dp.message(Ticket.waiting_for_name)
async def ticket_name(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Введите имя и фамилию.", reply_markup=cancel_kb)
        return
    await state.update_data(name=name)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить контакт", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Отправьте номер телефона:", reply_markup=kb)
    await state.set_state(Ticket.waiting_for_phone)

@dp.message(Ticket.waiting_for_phone, F.content_type == ContentType.CONTACT)
async def ticket_phone_contact(message: types.Message, state: FSMContext):
    if message.text == "Отмена":  # на всякий случай
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await ask_delivery_method(message, state)

@dp.message(Ticket.waiting_for_phone)
async def ticket_phone_text(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    phone = message.text.strip()
    if len(phone) < 6:
        await message.answer("Введите корректный номер.", reply_markup=cancel_kb)
        return
    await state.update_data(phone=phone)
    await ask_delivery_method(message, state)

async def ask_delivery_method(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="СДЭК"), KeyboardButton(text="Почта РФ")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Выберите службу доставки:", reply_markup=kb)
    await state.set_state(Ticket.waiting_for_method)

@dp.message(Ticket.waiting_for_method)
async def ticket_method(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    method = message.text.strip()
    if method not in ["СДЭК", "Почта РФ"]:
        await message.answer("Выберите СДЭК или Почта РФ", reply_markup=cancel_kb)
        return
    await state.update_data(method=method)
    await message.answer(f"Введите адрес отделения {method}:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Ticket.waiting_for_address)

@dp.message(Ticket.waiting_for_address)
async def ticket_address(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu_keyboard)
        return

    address = message.text.strip()
    if not address:
        await message.answer("Введите адрес.", reply_markup=cancel_kb)
        return

    await state.update_data(address=address)
    data = await state.get_data()
    required = ["photo", "name", "phone", "method", "address"]
    if any(k not in data for k in required):
        await message.answer("Ошибка: отсутствуют данные. Попробуйте начать заново.", reply_markup=menu_keyboard)
        await state.clear()
        return

    try:
        caption = (
            f"Новый тикет:\n"
            f"Имя: {data['name']}\n"
            f"Телефон: {data['phone']}\n"
            f"Доставка: {data['method']}\n"
            f"Адрес: {data['address']}"
        )
        await bot.send_photo(chat_id=ADMIN_ID, photo=data['photo'], caption=caption)
        await message.answer("Спасибо! Ваш заказ создан.", reply_markup=menu_keyboard)
    except Exception as e:
        logging.error(f"Ошибка при отправке админу: {e}")
        await message.answer("Ошибка при отправке тикета администратору.", reply_markup=menu_keyboard)
    finally:
        await state.clear()

# Запуск
if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))