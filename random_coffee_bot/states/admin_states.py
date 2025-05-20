from aiogram.fsm.state import State, StatesGroup


class FSMAdminPanel(StatesGroup):
    waiting_for_telegram_id = State()
    waiting_for_end_pause_date = State()
    waiting_for_text_of_notification = State()
    waiting_for_user_id = State()
    waiting_for_admin_id = State()
