import asyncio
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.stdout.reconfigure(encoding='utf-8')

os.environ["BOT_TOKEN"] = "123456789:TEST_MOCK_TOKEN"
import config
config.DB_PATH = BASE_DIR / "test_tutor_bot.db"

import database
from utils.time_utils import (
    format_datetime_for_display,
    format_short_date,
    parse_user_datetime
)

async def run_all_tests():
    print("--- Starting Tutor Bot Tests ---")
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()

    # 1. DB Init
    print("1. Testing database init...")
    await database.init_db()
    assert config.DB_PATH.exists(), "DB file was not created"

    # 2. Group creation and meeting link
    print("2. Testing group creation & meeting link...")
    group = await database.get_or_create_group(12345, "Test Group")
    assert group["chat_id"] == 12345
    assert group["chat_title"] == "Test Group"

    await database.set_meeting_link(12345, "https://meet.google.com/xyz-test")
    group_updated = await database.get_or_create_group(12345)
    assert group_updated["meeting_link"] == "https://meet.google.com/xyz-test"

    # 3. Recurring rules & generation
    print("3. Testing recurring schedule generation...")
    # Tuesday (1) and Thursday (3) at 18:00
    await database.add_recurring_rule(12345, 1, "18:00")
    await database.add_recurring_rule(12345, 3, "18:00")
    rules = await database.get_recurring_rules(12345)
    assert len(rules) == 2, f"Expected 2 rules, got {len(rules)}"

    await database.generate_recurring_lessons_for_group(12345, days_ahead=21)
    lessons = await database.get_all_lessons(12345, limit=50)
    print(f"Generated {len(lessons)} recurring lessons for the next 3 weeks.")
    assert len(lessons) > 0, "No lessons generated"

    # 4. Homework & Rescheduling
    print("4. Testing homework & rescheduling...")
    first_lesson = lessons[0]
    await database.update_lesson_homework(first_lesson["id"], "Read page 45-48, Grammar exercises 1-4")
    l_with_hw = await database.get_lesson_by_id(first_lesson["id"])
    assert "Grammar exercises" in l_with_hw["homework"]

    # Reschedule
    new_dt_utc = "2026-11-15 17:00:00"
    new_id = await database.reschedule_lesson(first_lesson["id"], new_dt_utc, "Alex (Student)")
    old_l = await database.get_lesson_by_id(first_lesson["id"])
    new_l = await database.get_lesson_by_id(new_id)

    assert old_l["status"] == "rescheduled"
    assert old_l["rescheduled_to_id"] == new_id
    assert old_l["rescheduled_by"] == "Alex (Student)"

    assert new_l["status"] == "scheduled"
    assert new_l["rescheduled_from_id"] == first_lesson["id"]
    assert "Grammar exercises" in new_l["homework"]

    # 5. Timezone formatting
    print("5. Testing timezone formatting (Kyiv + Abroad)...")
    dt_str = "2026-11-03 16:00:00" # 16:00 UTC -> 18:00 Kyiv, 17:00 Warsaw, 16:00 London
    fmt_kyiv = format_datetime_for_display(dt_str, "Europe/Kyiv", "")
    assert "18:00" in fmt_kyiv
    assert "Вівторок" in fmt_kyiv
    print("Kyiv display:", fmt_kyiv)

    fmt_dual = format_datetime_for_display(dt_str, "Europe/Kyiv", "Europe/Warsaw")
    assert "18:00 (Київ)" in fmt_dual
    assert "17:00 (Warsaw)" in fmt_dual
    print("Dual timezone display:", fmt_dual)

    # 6. Datetime parser
    print("6. Testing date/time user input parser...")
    parsed = parse_user_datetime("05.11 18:30", "Europe/Kyiv")
    assert parsed is not None
    dt_kyiv = parsed.astimezone(ZoneInfo("Europe/Kyiv"))
    assert dt_kyiv.day == 5 and dt_kyiv.month == 11 and dt_kyiv.hour == 18 and dt_kyiv.minute == 30

    parsed_tomorrow = parse_user_datetime("завтра 19:00", "Europe/Kyiv")
    assert parsed_tomorrow is not None

    # 7. Payment Balance & Deduction
    print("7. Testing payment balance and no-fee cancellation/rescheduling...")
    chat_id = 88888
    bal = await database.get_paid_balance(chat_id)
    assert bal == 0
    await database.add_paid_balance(chat_id, 4)
    bal = await database.get_paid_balance(chat_id)
    assert bal == 4

    l_id = await database.add_lesson(chat_id, "2026-11-20 17:00:00")
    # Cancelled: no fee deducted
    await database.update_lesson_status(l_id, "cancelled")
    bal_after_cancel = await database.get_paid_balance(chat_id)
    assert bal_after_cancel == 4, "Balance should not be deducted on cancel!"

    # Rescheduled: no fee deducted
    resched_id = await database.reschedule_lesson(l_id, "2026-11-21 17:00:00", "Teacher")
    bal_after_resched = await database.get_paid_balance(chat_id)
    assert bal_after_resched == 4, "Balance should not be deducted on reschedule!"

    # Completed: 1 lesson deducted!
    await database.update_lesson_status(resched_id, "completed")
    bal_after_completed = await database.get_paid_balance(chat_id)
    assert bal_after_completed == 3, f"Balance should be 3, got {bal_after_completed}"

    # Cleanup
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()

    print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
