from aiogram.fsm.state import State, StatesGroup


class FSMAdminPanal(StatesGroup):
    waiting_for_telegram_id = State()
