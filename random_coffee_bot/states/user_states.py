from aiogram.fsm.state import State, StatesGroup


class FSMUserForm(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_photo = State()
