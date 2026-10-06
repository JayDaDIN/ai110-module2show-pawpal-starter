"""Edge-case tests for sorting, recurrence and conflict detection.

The first three sections cover the behaviour the scheduler promises: tasks come
back in chronological order, completing a daily task queues tomorrow's copy, and
two pins wanting the same slot are flagged rather than silently dropped.

The last section holds regressions: cases the implementation once got wrong —
midnight-crossing conflicts, duplicate successors, a plan editing the tasks it
was only meant to read, a renamed pet going missing, an empty day reading as an
unlimited one, and a mistyped filter matching everything.
"""

from datetime import date, timedelta

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task

MONDAY = date(2026, 10, 5)
TUESDAY = MONDAY + timedelta(days=1)


def owner_with(*tasks, **kwargs):
    """An owner with one pet, Mochi, holding these tasks."""
    kwargs.setdefault("available_minutes", 240)
    return Owner("Jordan", pets=[Pet("Mochi", tasks=list(tasks))], **kwargs)


# --- sorting correctness -----------------------------------------------------


def test_a_built_plan_reads_in_chronological_order():
    """Whatever order tasks were entered in, the plan comes back on the clock."""
    owner = owner_with(
        Task("Evening meds", 10, fixed_time="19:00"),
        Task("Lunch", 15, fixed_time="12:30"),
        Task("Breakfast", 10, fixed_time="07:30"),
    )

    plan = Scheduler(owner).build_plan(MONDAY)

    times = [slot["start_time"] for slot in plan]
    assert times == sorted(times)
    assert times == ["07:30", "12:30", "19:00"]


def test_chronological_order_holds_across_pets():
    """A plan spanning several pets is ordered by time, not grouped by pet."""
    owner = Owner(
        "Jordan",
        available_minutes=240,
        pets=[
            Pet("Mochi", tasks=[Task("Cat meds", 5, fixed_time="08:00")]),
            Pet("Rex", tasks=[Task("Dog walk", 30, fixed_time="07:00")]),
        ],
    )

    plan = Scheduler(owner).build_plan(MONDAY)

    assert [(s["start_time"], s["pet"]) for s in plan] == [
        ("07:00", "Rex"),
        ("08:00", "Mochi"),
    ]


def test_flexible_tasks_are_ordered_by_the_time_they_were_given():
    """Tasks with no fixed time still come back in the order they were placed."""
    owner = owner_with(
        Task("Anchor", 30, fixed_time="09:00"),
        Task("Brush", 20, priority="low"),
        Task("Meds", 10, priority="high"),
    )

    plan = Scheduler(owner).build_plan(MONDAY)

    times = [slot["start_time"] for slot in plan]
    assert times == sorted(times)
    # Meds outranks Brush, so it is placed first and takes 08:00; Brush then
    # takes 08:10, and both still fit before the 09:00 anchor.
    assert [slot["description"] for slot in plan] == ["Meds", "Brush", "Anchor"]
    assert times == ["08:00", "08:10", "09:00"]


def test_sorting_a_task_list_by_time_is_stable_for_identical_tasks():
    """Two tasks that tie on every key still produce a deterministic order."""
    first = Task("Feeding", 10, fixed_time="08:00")
    second = Task("Feeding", 10, fixed_time="08:00")

    ordered = sorted([first, second], key=lambda t: t.time_sort_key())

    assert [id(t) for t in ordered] == [id(first), id(second)]


# --- recurrence logic --------------------------------------------------------


def test_completing_a_daily_task_creates_one_due_the_following_day():
    """The core recurrence promise: tick it off today, it returns tomorrow."""
    pet = Pet("Mochi")
    pet.add_task(Task("Feeding", 10, frequency="daily"))

    successor = pet.complete_task("Feeding", on=MONDAY)

    assert successor.due_date == TUESDAY
    assert successor.completed is False
    assert successor.is_due_on(TUESDAY) is True
    assert successor.is_due_on(MONDAY) is False


def test_the_original_is_retired_so_exactly_one_copy_stays_pending():
    """Completing a daily task leaves one live copy, not zero and not two."""
    pet = Pet("Mochi")
    pet.add_task(Task("Feeding", 10, frequency="daily"))

    pet.complete_task("Feeding", on=MONDAY)

    assert len(pet.tasks) == 2
    live = [t for t in pet.tasks if not t.retired]
    assert len(live) == 1
    assert live[0].due_date == TUESDAY


def test_tomorrows_copy_is_planned_tomorrow_and_not_today():
    """The successor is invisible to today's plan and present in tomorrow's."""
    owner = owner_with(Task("Feeding", 10, frequency="daily"))
    pet = owner.get_pet("Mochi")
    scheduler = Scheduler(owner)

    pet.complete_task("Feeding", on=MONDAY)

    assert [s["description"] for s in scheduler.build_plan(MONDAY)] == []
    assert [s["description"] for s in scheduler.build_plan(TUESDAY)] == ["Feeding"]


def test_the_successor_keeps_every_setting_of_the_task_it_replaces():
    """A recurring task does not quietly lose its pin, priority or category."""
    pet = Pet("Mochi")
    pet.add_task(
        Task(
            "Insulin",
            5,
            priority="high",
            category="meds",
            fixed_time="08:00",
            preferred_time="morning",
            frequency="daily",
        )
    )

    successor = pet.complete_task("Insulin", on=MONDAY)

    assert successor.priority == "high"
    assert successor.category == "meds"
    assert successor.fixed_time == "08:00"
    assert successor.preferred_time == "morning"
    assert successor.interval_days == 1


def test_a_daily_task_chains_day_after_day():
    """Completing the successor queues the day after, so the chain continues.

    Each round completes the Task object the previous one returned; completing
    by description works too, since the lookup now skips retired copies.
    """
    pet = Pet("Mochi")
    pending = pet.add_task(Task("Feeding", 10, frequency="daily"))

    day = MONDAY
    for _ in range(3):
        pending = pet.complete_task(pending, on=day)
        day += timedelta(days=1)
        assert pending.due_date == day

    live = [t for t in pet.tasks if not t.retired]
    assert len(live) == 1
    assert live[0] is pending


# --- conflict detection ------------------------------------------------------


def test_two_tasks_pinned_to_the_same_time_are_flagged():
    """The headline case: the same slot booked twice for one pet."""
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Vet call", 30, fixed_time="08:00"),
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan(MONDAY)

    assert scheduler.has_conflicts() is True
    assert len(scheduler.find_conflicts()) == 1
    assert len(scheduler.conflict_warnings()) == 1
    assert "08:00" in scheduler.conflict_warnings()[0]


def test_a_duplicate_time_across_two_pets_is_flagged():
    """One owner cannot walk two dogs at once, even in different rooms."""
    owner = Owner(
        "Jordan",
        available_minutes=240,
        pets=[
            Pet("Mochi", tasks=[Task("Cat meds", 15, fixed_time="08:00")]),
            Pet("Rex", tasks=[Task("Dog walk", 15, fixed_time="08:00")]),
        ],
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan(MONDAY)

    pet_a, task_a, pet_b, task_b = scheduler.find_conflicts()[0]
    assert {pet_a.name, pet_b.name} == {"Mochi", "Rex"}
    assert "both booked" in scheduler.conflict_warnings()[0]


def test_only_one_of_two_duplicate_pins_is_scheduled():
    """A flagged clash is also resolved: the loser is skipped with a reason."""
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00", priority="low"),
        Task("Insulin", 30, fixed_time="08:00", priority="high"),
    )
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan(MONDAY)

    assert [slot["description"] for slot in plan] == ["Insulin"]
    assert [item["description"] for item in scheduler.skipped] == ["Walk"]
    assert "overlaps Insulin" in scheduler.skipped[0]["reason"]


def test_partial_overlap_counts_as_a_conflict():
    """Clashes are not only exact duplicates: 08:00+30 collides with 08:15."""
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Grooming", 30, fixed_time="08:15"),
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan(MONDAY)

    assert scheduler.has_conflicts() is True


def test_identical_times_on_different_days_do_not_conflict():
    """A weekly 08:00 task and a daily one only clash on the day both are due."""
    weekly = Task("Bath", 30, fixed_time="08:00", frequency="weekly")
    weekly.mark_complete(MONDAY)
    owner = owner_with(Task("Feeding", 30, fixed_time="08:00"), weekly)
    scheduler = Scheduler(owner)

    scheduler.build_plan(TUESDAY)  # the bath is not due again until next Monday

    assert scheduler.has_conflicts() is False


def test_a_clean_day_reports_no_conflicts():
    """No false positives on back-to-back tasks that merely touch."""
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Feeding", 10, fixed_time="08:30"),
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan(MONDAY)

    assert scheduler.has_conflicts() is False
    assert scheduler.conflict_warnings() == []


# --- regressions -------------------------------------------------------------
# Each of these reproduced a bug that is now fixed.


def test_a_task_crossing_midnight_conflicts_with_an_early_one():
    owner = owner_with(
        Task("Late walk", 30, fixed_time="23:50"),  # runs to 00:20
        Task("Midnight meds", 20, fixed_time="00:05"),
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan(MONDAY)

    assert scheduler.has_conflicts() is True


def test_completing_a_task_twice_does_not_duplicate_the_successor():
    pet = Pet("Mochi")
    pet.add_task(Task("Feeding", 10, frequency="daily"))

    pet.complete_task("Feeding", on=MONDAY)
    pet.complete_task("Feeding", on=MONDAY)

    assert len([t for t in pet.tasks if not t.retired]) == 1


def test_planning_tomorrow_leaves_todays_completions_alone():
    owner = owner_with(Task("Walk", 20, frequency="daily"))
    pet = owner.get_pet("Mochi")
    pet.tasks[0].mark_complete(MONDAY)

    Scheduler(owner).build_plan(TUESDAY)

    assert len(pet.completed_tasks()) == 1


def test_a_renamed_pet_is_still_findable():
    owner = Owner("Jordan", pets=[Pet("Old")])

    owner.pets[0].name = "New"

    assert owner.get_pet("New") is not None
    assert owner.get_pet("Old") is None


def test_a_day_that_starts_and_ends_at_the_same_time_has_no_room():
    owner = owner_with(Task("Walk", 20), day_start="08:00", day_end="08:00")

    plan = Scheduler(owner).build_plan(MONDAY)

    assert plan == []


def test_an_unrecognised_status_filter_is_rejected():
    pet = Pet("Mochi", tasks=[Task("Walk", 20)])

    with pytest.raises(ValueError):
        pet.filter_tasks(status="garbage")
