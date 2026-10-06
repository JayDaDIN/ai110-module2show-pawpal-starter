"""Tests for the four scheduling features: time ordering, filtering,
recurrence, and conflict detection."""

from datetime import date, timedelta

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task

MONDAY = date(2026, 10, 5)


def owner_with(*tasks, **kwargs):
    """An owner with one pet, Mochi, holding these tasks."""
    kwargs.setdefault("available_minutes", 240)
    return Owner("Jordan", pets=[Pet("Mochi", tasks=list(tasks))], **kwargs)


def descriptions(slots):
    return [slot["description"] for slot in slots]


def times(slots):
    return [slot["start_time"] for slot in slots]


# --- sorting tasks by time ---------------------------------------------------


def test_time_sort_key_puts_pinned_tasks_in_clock_order():
    late = Task("Dinner", 10, fixed_time="18:00")
    early = Task("Breakfast", 10, fixed_time="07:00")
    flexible = Task("Walk", 30)

    ordered = sorted([flexible, late, early], key=lambda t: t.time_sort_key())

    # Flexible tasks have no time yet, so they sort after everything pinned.
    assert [t.description for t in ordered] == ["Breakfast", "Dinner", "Walk"]


def test_flexible_tasks_still_fall_back_to_priority_order():
    low = Task("Brush", 10, priority="low")
    high = Task("Meds", 10, priority="high")

    ordered = sorted([low, high], key=lambda t: t.time_sort_key())

    assert [t.description for t in ordered] == ["Meds", "Brush"]


def test_pet_can_list_its_tasks_on_the_clock():
    pet = Pet(
        "Mochi",
        tasks=[Task("Walk", 30), Task("Meds", 5, fixed_time="09:00")],
    )

    assert [t.description for t in pet.tasks_by_time()] == ["Meds", "Walk"]


def test_owner_can_order_a_filtered_list_by_time_across_pets():
    owner = Owner(
        "Jordan",
        pets=[
            Pet("Mochi", tasks=[Task("Dinner", 10, fixed_time="18:00")]),
            Pet("Biscuit", tasks=[Task("Meds", 5, fixed_time="08:00")]),
        ],
    )

    pairs = owner.filter_tasks(by_time=True)

    assert [t.description for _, t in pairs] == ["Meds", "Dinner"]


# --- filtering by pet and status ---------------------------------------------


def test_filter_tasks_narrows_by_pet():
    owner = Owner(
        "Jordan",
        pets=[
            Pet("Mochi", tasks=[Task("Litter box", 10)]),
            Pet("Biscuit", tasks=[Task("Walk", 30)]),
        ],
    )

    assert [t.description for _, t in owner.filter_tasks(pet="Mochi")] == ["Litter box"]
    assert owner.filter_tasks(pet="Nobody") == []


def test_filter_tasks_narrows_by_status():
    owner = owner_with(Task("Walk", 30), Task("Feed", 10))
    owner.pets[0].tasks[1].mark_complete()

    assert [t.description for _, t in owner.filter_tasks(status="pending")] == ["Walk"]
    assert [t.description for _, t in owner.filter_tasks(status="done")] == ["Feed"]


def test_filters_combine():
    owner = owner_with(
        Task("Walk", 30, category="walk"),
        Task("Evening walk", 20, category="walk"),
        Task("Meds", 5, category="meds"),
    )
    owner.pets[0].tasks[0].mark_complete()

    pairs = owner.filter_tasks(pet="Mochi", status="pending", category="walk")

    assert [t.description for _, t in pairs] == ["Evening walk"]


def test_filter_by_whether_a_task_is_pinned():
    owner = owner_with(Task("Meds", 5, fixed_time="08:00"), Task("Walk", 30))

    assert [t.description for _, t in owner.filter_tasks(anchored=True)] == ["Meds"]
    assert [t.description for _, t in owner.filter_tasks(anchored=False)] == ["Walk"]


def test_categories_lists_only_what_is_in_use():
    owner = owner_with(Task("Walk", 30, category="walk"), Task("Meds", 5, category="meds"))

    assert owner.categories() == ["meds", "walk"]


def test_deleting_by_position_removes_the_row_you_clicked():
    # Two tasks share a description, so removing by name would delete the wrong
    # one — which is exactly what the UI used to do.
    pet = Pet("Mochi", tasks=[Task("Walk", 30), Task("Walk", 15)])

    removed = pet.remove_task_at(1)

    assert removed.duration_minutes == 15
    assert [t.duration_minutes for t in pet.tasks] == [30]
    assert pet.remove_task_at(9) is None


# --- recurring tasks ---------------------------------------------------------


def test_a_weekly_task_is_not_replanned_the_next_day():
    weekly = Task("Grooming", 45, frequency="weekly")
    weekly.mark_complete(on=MONDAY)
    scheduler = Scheduler(owner_with(weekly))

    scheduler.build_plan(on_date=MONDAY + timedelta(days=1))

    assert scheduler.scheduled == []
    assert "weekly" in scheduler.skipped[0]["reason"]


def test_a_weekly_task_comes_back_once_its_interval_has_passed():
    weekly = Task("Grooming", 45, frequency="weekly")
    weekly.mark_complete(on=MONDAY)
    scheduler = Scheduler(owner_with(weekly))

    assert descriptions(scheduler.build_plan(on_date=MONDAY + timedelta(days=7))) == [
        "Grooming"
    ]


def test_a_daily_task_ticked_off_today_comes_back_tomorrow():
    daily = Task("Feeding", 10)
    daily.mark_complete(on=MONDAY)
    scheduler = Scheduler(owner_with(daily))

    assert scheduler.build_plan(on_date=MONDAY) == []
    assert descriptions(scheduler.build_plan(on_date=MONDAY + timedelta(days=1))) == [
        "Feeding"
    ]


def test_a_custom_interval_repeats_on_its_own_schedule():
    meds = Task("Flea treatment", 5, frequency="custom", interval_days=3)
    meds.mark_complete(on=MONDAY)
    scheduler = Scheduler(owner_with(meds))

    assert scheduler.build_plan(on_date=MONDAY + timedelta(days=2)) == []
    assert descriptions(scheduler.build_plan(on_date=MONDAY + timedelta(days=3))) == [
        "Flea treatment"
    ]
    assert meds.repeat_text() == "every 3 days"


def test_marking_a_task_incomplete_makes_it_due_again_at_once():
    weekly = Task("Grooming", 45, frequency="weekly")
    weekly.mark_complete(on=MONDAY)
    weekly.mark_incomplete()

    assert weekly.is_due_on(MONDAY) is True
    assert weekly.last_completed is None


def test_a_custom_frequency_without_an_interval_is_rejected():
    with pytest.raises(ValueError):
        Task("Flea treatment", 5, frequency="custom")


def test_an_interval_that_contradicts_its_frequency_is_rejected():
    with pytest.raises(ValueError):
        Task("Grooming", 45, frequency="weekly", interval_days=3)


@pytest.mark.parametrize("bad", [0, -1, "three"])
def test_a_bad_interval_is_rejected(bad):
    with pytest.raises(ValueError):
        Task("Grooming", 45, frequency="custom", interval_days=bad)


# --- conflict detection ------------------------------------------------------


def test_a_higher_priority_pin_keeps_a_contested_slot():
    # The old rule was "earliest wins", which let a long low-priority grooming
    # session bump the insulin.
    owner = owner_with(
        Task("Brush", 60, priority="low", fixed_time="08:00"),
        Task("Insulin", 5, priority="high", fixed_time="08:30"),
    )
    scheduler = Scheduler(owner)

    assert descriptions(scheduler.build_plan()) == ["Insulin"]
    assert scheduler.skipped[0]["description"] == "Brush"
    assert "overlaps" in scheduler.skipped[0]["reason"]


def test_equal_priority_still_keeps_the_earlier_pin():
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Groom", 20, fixed_time="08:10"),
    )
    scheduler = Scheduler(owner)

    assert descriptions(scheduler.build_plan()) == ["Walk"]
    assert scheduler.skipped[0]["description"] == "Groom"


def test_the_skip_reason_names_the_task_that_won():
    owner = owner_with(
        Task("Brush", 60, priority="low", fixed_time="08:00"),
        Task("Insulin", 5, priority="high", fixed_time="08:30"),
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    assert "Insulin" in scheduler.skipped[0]["reason"]


def test_overlapping_pins_are_found_before_a_plan_is_built():
    owner = Owner(
        "Jordan",
        pets=[
            Pet("Mochi", tasks=[Task("Feeding", 10, fixed_time="08:00")]),
            Pet("Biscuit", tasks=[Task("Meds", 5, fixed_time="08:05")]),
        ],
    )

    clashes = owner.all_conflicts()

    assert len(clashes) == 1
    pet_a, task_a, pet_b, task_b = clashes[0]
    assert (pet_a.name, task_a.description) == ("Mochi", "Feeding")
    assert (pet_b.name, task_b.description) == ("Biscuit", "Meds")


def test_conflicts_with_checks_a_task_that_is_not_added_yet():
    owner = owner_with(Task("Feeding", 10, fixed_time="08:00"))

    assert [t.description for _, t in owner.conflicts_with(Task("Meds", 5, fixed_time="08:05"))] == [
        "Feeding"
    ]
    assert owner.conflicts_with(Task("Meds", 5, fixed_time="08:10")) == []
    assert owner.conflicts_with(Task("Walk", 30)) == []


def test_tasks_touching_end_to_end_do_not_conflict():
    first = Task("Walk", 30, fixed_time="08:00")
    second = Task("Groom", 20, fixed_time="08:30")

    assert first.overlaps(second) is False
    assert second.overlaps(first) is False


def test_a_pet_can_list_its_own_clashes():
    pet = Pet(
        "Mochi",
        tasks=[Task("Feeding", 20, fixed_time="08:00"), Task("Meds", 5, fixed_time="08:10")],
    )

    assert [(a.description, b.description) for a, b in pet.anchor_conflicts()] == [
        ("Feeding", "Meds")
    ]


# --- the owner's day and preferred windows -----------------------------------


def test_a_flexible_task_lands_in_its_preferred_window():
    owner = owner_with(
        Task("Evening walk", 20, preferred_time="evening"),
        Task("Litter box", 10),
        day_start="07:30",
    )

    plan = Scheduler(owner).build_plan()

    assert list(zip(descriptions(plan), times(plan))) == [
        ("Litter box", "07:30"),
        ("Evening walk", "17:00"),
    ]


def test_a_task_still_gets_planned_when_its_window_has_no_room():
    # Better outside the preferred window than not at all.
    owner = owner_with(
        Task("Evening walk", 20, preferred_time="evening"),
        day_start="07:30",
        day_end="09:00",
    )

    assert times(Scheduler(owner).build_plan()) == ["07:30"]


def test_nothing_is_scheduled_past_the_end_of_the_day():
    owner = owner_with(
        Task("Walk", 30, priority="high"),
        Task("Hike", 90, priority="medium"),
        available_minutes=500,
        day_start="21:00",
        day_end="22:00",
    )
    scheduler = Scheduler(owner)

    assert times(scheduler.build_plan()) == ["21:00"]
    assert scheduler.skipped[0]["description"] == "Hike"
    assert "22:00" in scheduler.skipped[0]["reason"]


def test_an_end_before_the_start_means_the_day_runs_to_midnight():
    owner = owner_with(Task("Walk", 30), day_start="23:00", day_end="06:00")

    assert times(Scheduler(owner).build_plan()) == ["23:00"]


def test_a_gap_is_filled_from_both_sides():
    # A task placed in the middle of a gap leaves usable time before and after.
    owner = owner_with(
        Task("Lunch walk", 30, priority="high", preferred_time="afternoon"),
        Task("Brush", 10, priority="medium"),
        Task("Play", 10, priority="low"),
        day_start="08:00",
    )

    plan = Scheduler(owner).build_plan()

    assert list(zip(descriptions(plan), times(plan))) == [
        ("Brush", "08:00"),
        ("Play", "08:10"),
        ("Lunch walk", "12:00"),
    ]


# --- stale plans -------------------------------------------------------------


def test_a_plan_knows_when_the_owner_changed_underneath_it():
    owner = owner_with(Task("Walk", 30))
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    assert scheduler.is_stale() is False

    owner.set_available_minutes(10)

    assert scheduler.is_stale() is True
    scheduler.build_plan()
    assert scheduler.is_stale() is False


def test_setting_a_value_it_already_has_is_not_a_change():
    # Streamlit replays the whole script on every click, so the setters are
    # called again with the values they already hold.
    owner = owner_with(Task("Walk", 30))
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    owner.rename(owner.name)
    owner.set_available_minutes(owner.available_minutes)
    owner.set_day_start(owner.day_start)
    owner.set_preferred_times(owner.preferred_times)
    owner.set_skip_low_priority(owner.skip_low_priority)

    assert scheduler.is_stale() is False


# --- Scheduler.sort_by_time -------------------------------------------------


def test_scheduler_sort_by_time_puts_pinned_tasks_in_clock_order():
    # Added deliberately out of order.
    mochi = Pet(
        "Mochi",
        tasks=[Task("Play", 20, fixed_time="18:00"), Task("Feeding", 10, fixed_time="07:30")],
    )
    biscuit = Pet("Biscuit", tasks=[Task("Meds", 5, fixed_time="12:00")])
    scheduler = Scheduler(Owner("Jordan", pets=[mochi, biscuit]))

    assert [t.description for _, t in scheduler.sort_by_time()] == [
        "Feeding",
        "Meds",
        "Play",
    ]


def test_scheduler_sort_by_time_puts_flexible_tasks_after_pinned_ones():
    pet = Pet("Mochi", tasks=[Task("Litter box", 10), Task("Feeding", 10, fixed_time="07:30")])
    scheduler = Scheduler(Owner("Jordan", pets=[pet]))

    assert [t.description for _, t in scheduler.sort_by_time()] == [
        "Feeding",
        "Litter box",
    ]


def test_scheduler_sort_by_time_accepts_an_explicit_list_of_pairs():
    pet = Pet(
        "Mochi",
        tasks=[Task("B", 10, fixed_time="09:00"), Task("A", 10, fixed_time="08:00")],
    )
    scheduler = Scheduler(Owner("Jordan", pets=[pet]))
    pairs = scheduler.filter_tasks(pet="Mochi")

    assert [t.description for _, t in scheduler.sort_by_time(pairs)] == ["A", "B"]


# --- Scheduler.filter_tasks -------------------------------------------------


def test_scheduler_filters_by_pet_name_and_completion_status():
    mochi = Pet("Mochi", tasks=[Task("Feeding", 10), Task("Litter box", 10)])
    biscuit = Pet("Biscuit", tasks=[Task("Walk", 30)])
    mochi.tasks[1].mark_complete()
    scheduler = Scheduler(Owner("Jordan", pets=[mochi, biscuit]))

    assert [t.description for _, t in scheduler.filter_tasks(pet="Mochi")] == [
        "Feeding",
        "Litter box",
    ]
    assert [t.description for _, t in scheduler.filter_tasks(status="done")] == [
        "Litter box"
    ]
    assert [t.description for _, t in scheduler.filter_tasks(status="pending")] == [
        "Feeding",
        "Walk",
    ]
    assert scheduler.filter_tasks(pet="Biscuit", status="done") == []


# --- recurrence: completing a task spawns a brand new instance --------------


def test_completing_a_daily_task_queues_a_new_instance_for_tomorrow():
    pet = Pet("Mochi", tasks=[Task("Feeding", 10, frequency="daily")])
    original = pet.tasks[0]

    successor = pet.complete_task(original, on=MONDAY)

    assert len(pet.tasks) == 2
    assert successor is not original  # a genuinely new object
    assert successor.description == "Feeding"
    assert successor.completed is False
    assert successor.due_date == MONDAY + timedelta(days=1)
    assert original.completed is True
    assert original.retired is True


def test_completing_a_weekly_task_queues_one_seven_days_out():
    pet = Pet("Mochi", tasks=[Task("Grooming", 20, frequency="weekly")])

    successor = pet.complete_task("Grooming", on=MONDAY)

    assert successor.due_date == MONDAY + timedelta(days=7)
    assert successor.repeat_text() == "weekly"


def test_the_successor_carries_the_settings_of_the_original():
    pet = Pet(
        "Mochi",
        tasks=[
            Task(
                "Meds",
                5,
                priority="high",
                category="meds",
                fixed_time="08:00",
                preferred_time="morning",
                frequency="daily",
            )
        ],
    )

    successor = pet.complete_task("Meds", on=MONDAY)

    assert successor.priority == "high"
    assert successor.category == "meds"
    assert successor.fixed_time == "08:00"
    assert successor.preferred_time == "morning"
    assert successor.is_anchored() is True


def test_the_successor_is_planned_tomorrow_and_not_today():
    pet = Pet("Mochi", tasks=[Task("Feeding", 10, priority="high")])
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))
    pet.complete_task("Feeding", on=MONDAY)

    today = [s["description"] for s in scheduler.build_plan(on_date=MONDAY)]
    tomorrow = [
        s["description"] for s in scheduler.build_plan(on_date=MONDAY + timedelta(days=1))
    ]

    assert today == []
    assert tomorrow == ["Feeding"]  # exactly one, not the retired copy as well


def test_a_retired_task_never_comes_back():
    pet = Pet("Mochi", tasks=[Task("Feeding", 10, priority="high")])
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))
    original = pet.tasks[0]
    pet.complete_task(original, on=MONDAY)

    for offset in range(1, 5):
        plan = scheduler.build_plan(on_date=MONDAY + timedelta(days=offset))
        assert [s["description"] for s in plan].count("Feeding") <= 1
    assert original.completed is True  # the daily rollover never un-ticks it


def test_complete_task_rejects_a_task_that_belongs_to_another_pet():
    mochi = Pet("Mochi", tasks=[Task("Feeding", 10)])
    biscuit = Pet("Biscuit", tasks=[Task("Walk", 30)])

    with pytest.raises(ValueError):
        mochi.complete_task(biscuit.tasks[0], on=MONDAY)
    with pytest.raises(ValueError):
        mochi.complete_task("Nonexistent", on=MONDAY)


# --- conflict detection warns rather than crashing --------------------------


def test_two_tasks_at_the_same_time_warn_instead_of_raising():
    pet = Pet(
        "Mochi",
        tasks=[
            Task("Feeding", 10, fixed_time="07:30"),
            Task("Brushing", 10, fixed_time="07:30"),
        ],
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))

    warnings = scheduler.conflict_warnings()

    assert scheduler.has_conflicts() is True
    assert len(warnings) == 1
    assert "WARNING" in warnings[0]
    assert "double-booked" in warnings[0]
    # The program keeps going: the plan still builds, one task is skipped.
    plan = scheduler.build_plan()
    assert len(plan) == 1
    assert len(scheduler.skipped) == 1


def test_a_clash_between_two_different_pets_is_detected():
    mochi = Pet("Mochi", tasks=[Task("Feeding", 10, fixed_time="07:30")])
    biscuit = Pet("Biscuit", tasks=[Task("Breakfast", 10, fixed_time="07:35")])
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[mochi, biscuit]))

    warnings = scheduler.conflict_warnings()

    assert len(warnings) == 1
    assert "Mochi and Biscuit" in warnings[0]


def test_no_conflicts_gives_an_empty_warning_list():
    pet = Pet(
        "Mochi",
        tasks=[
            Task("Feeding", 10, fixed_time="07:30"),
            Task("Walk", 30, fixed_time="07:40"),  # starts exactly as feeding ends
        ],
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))

    assert scheduler.conflict_warnings() == []
    assert scheduler.has_conflicts() is False


def test_a_completed_task_is_not_reported_as_a_conflict():
    pet = Pet(
        "Mochi",
        tasks=[
            Task("Feeding", 10, fixed_time="07:30"),
            Task("Brushing", 10, fixed_time="07:30"),
        ],
    )
    pet.tasks[1].mark_complete()
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))

    assert scheduler.conflict_warnings() == []


def test_a_recurring_task_does_not_conflict_with_its_own_successor():
    # The successor is pinned to the same time but is due tomorrow, so
    # reporting the two against each other would be nonsense.
    pet = Pet("Mochi", tasks=[Task("Feeding", 10, fixed_time="07:30")])
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))
    pet.complete_task("Feeding", on=MONDAY)
    scheduler.build_plan(on_date=MONDAY)

    assert scheduler.conflict_warnings() == []


def test_conflict_warnings_appear_in_the_explanation():
    pet = Pet(
        "Mochi",
        tasks=[
            Task("Feeding", 10, fixed_time="07:30"),
            Task("Brushing", 10, fixed_time="07:30"),
        ],
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=200, pets=[pet]))
    scheduler.build_plan()

    assert any("WARNING" in line for line in scheduler.explain())
