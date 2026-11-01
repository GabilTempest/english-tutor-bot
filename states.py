from aiogram.fsm.state import State, StatesGroup

class AddLessonStates(StatesGroup):
    waiting_for_datetime = State()
    waiting_for_hw = State()

class RescheduleStates(StatesGroup):
    waiting_for_new_datetime = State()

class HomeworkStates(StatesGroup):
    waiting_for_text = State()

class SettingsStates(StatesGroup):
    waiting_for_meeting_link = State()
    waiting_for_schedule_rules = State()
    waiting_for_timezones = State()

class ClearHistoryStates(StatesGroup):
    waiting_for_password = State()

class EditHistoryStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_datetime = State()
    waiting_for_new_hw = State()

class BalanceStates(StatesGroup):
    waiting_for_add_amount = State()
    waiting_for_set_amount = State()
