"""Tests for the scheduling brain: ordering, anchoring, budget and explanation."""

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task


def owner_with(*tasks, **kwargs):
    """An owner with one pet, Mochi, holding these tasks."""
    kwargs.setdefault("available_minutes", 240)
    return Owner("Jordan", pets=[Pet("Mochi", tasks=list(tasks))], **kwargs)


def descriptions(slots):
    return [slot["description"] for slot in slots]


def times(slots):
    return [slot["start_time"] for slot in slots]


# --- ordering ----------------------------------------------------------------


def test_high_priority_tasks_are_scheduled_first():
    owner = owner_with(
        Task("Brush", 10, priority="low"),
        Task("Play", 10, priority="medium"),
        Task("Meds", 10, priority="high"),
    )

    assert descriptions(Scheduler(owner).build_plan()) == ["Meds", "Play", "Brush"]


def test_equal_priority_breaks_tie_by_shortest_duration():
    owner = owner_with(
        Task("Long walk", 30, priority="high"),
        Task("Feeding", 10, priority="high"),
    )

    assert descriptions(Scheduler(owner).build_plan()) == ["Feeding", "Long walk"]


def test_start_times_advance_by_each_task_duration():
    owner = owner_with(
        Task("Feed", 30, priority="high"),
        Task("Walk", 45, priority="medium"),
        Task("Brush", 15, priority="low"),
        day_start="08:00",
    )

    assert times(Scheduler(owner).build_plan()) == ["08:00", "08:30", "09:15"]


def test_start_times_cross_the_hour_boundary_correctly():
    owner = owner_with(
        Task("Walk", 30, priority="high"),
        Task("Feed", 30, priority="medium"),
        day_start="08:45",
    )

    assert times(Scheduler(owner).build_plan()) == ["08:45", "09:15"]


# --- the shared time budget --------------------------------------------------


def test_plan_never_exceeds_the_time_budget():
    owner = owner_with(
        Task("Walk", 45, priority="high"),
        Task("Groom", 45, priority="medium"),
        Task("Train", 45, priority="low"),
        available_minutes=60,
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    assert scheduler.total_scheduled_minutes() <= 60


def test_task_that_does_not_fit_is_skipped_with_a_reason():
    owner = owner_with(Task("Long hike", 90, priority="high"), available_minutes=30)
    scheduler = Scheduler(owner)

    assert scheduler.build_plan() == []
    assert len(scheduler.skipped) == 1
    assert scheduler.skipped[0]["description"] == "Long hike"
    assert "90 min" in scheduler.skipped[0]["reason"]


def test_shorter_task_still_fits_after_a_longer_one_is_skipped():
    # This is the behavior that proves the scheduler continues past a task that
    # does not fit rather than stopping at the first overflow.
    owner = owner_with(
        Task("Hike", 50, priority="high"),
        Task("Groom", 30, priority="high"),
        Task("Feed", 10, priority="high"),
        available_minutes=60,
    )
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan()

    # Sorted shortest-first within "high": Feed (10), Groom (30), Hike (50).
    assert descriptions(plan) == ["Feed", "Groom"]
    assert [s["description"] for s in scheduler.skipped] == ["Hike"]
    assert scheduler.total_scheduled_minutes() == 40


def test_zero_available_minutes_skips_everything():
    owner = owner_with(Task("Feed", 5, priority="high"), available_minutes=0)
    scheduler = Scheduler(owner)

    assert scheduler.build_plan() == []
    assert len(scheduler.skipped) == 1


# --- fixed-time (anchored) tasks ---------------------------------------------


def test_anchored_task_is_placed_at_its_fixed_time():
    owner = owner_with(Task("Meds", 10, fixed_time="14:00"), day_start="08:00")

    assert times(Scheduler(owner).build_plan()) == ["14:00"]


def test_flexible_tasks_fill_the_gap_before_an_anchor():
    owner = owner_with(
        Task("Meds", 10, priority="high", fixed_time="09:00"),
        Task("Walk", 30, priority="high"),
        day_start="08:00",
    )
    plan = Scheduler(owner).build_plan()

    # Walk fits in the 08:00-09:00 gap, so it runs before the pinned meds.
    assert list(zip(descriptions(plan), times(plan))) == [
        ("Walk", "08:00"),
        ("Meds", "09:00"),
    ]


def test_flexible_task_too_long_for_the_gap_goes_after_the_anchor():
    owner = owner_with(
        Task("Meds", 10, priority="high", fixed_time="08:30"),
        Task("Long walk", 60, priority="high"),
        day_start="08:00",
    )
    plan = Scheduler(owner).build_plan()

    # A 60-min walk cannot fit the 30-min gap, so it starts after meds end.
    assert list(zip(descriptions(plan), times(plan))) == [
        ("Meds", "08:30"),
        ("Long walk", "08:40"),
    ]


def test_anchored_tasks_are_placed_even_when_lower_priority_than_flexible_ones():
    owner = owner_with(
        Task("Brush", 15, priority="low", fixed_time="08:00"),
        Task("Meds", 5, priority="high"),
        day_start="08:00",
    )
    plan = Scheduler(owner).build_plan()

    # The anchor claims 08:00; the high-priority flexible task follows it.
    assert list(zip(descriptions(plan), times(plan))) == [
        ("Brush", "08:00"),
        ("Meds", "08:15"),
    ]


def test_overlapping_anchors_keep_the_earlier_one():
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Groom", 20, fixed_time="08:10"),
        day_start="08:00",
    )
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan()

    assert descriptions(plan) == ["Walk"]
    assert scheduler.skipped[0]["description"] == "Groom"
    assert "overlaps" in scheduler.skipped[0]["reason"]


def test_anchors_touching_end_to_end_do_not_count_as_overlapping():
    owner = owner_with(
        Task("Walk", 30, fixed_time="08:00"),
        Task("Groom", 20, fixed_time="08:30"),
        day_start="08:00",
    )
    scheduler = Scheduler(owner)

    assert descriptions(scheduler.build_plan()) == ["Walk", "Groom"]
    assert scheduler.skipped == []


def test_anchored_tasks_count_against_the_shared_budget():
    owner = owner_with(
        Task("Meds", 40, fixed_time="08:00"),
        Task("Walk", 30, priority="high"),
        available_minutes=60,
        day_start="08:00",
    )
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan()

    assert descriptions(plan) == ["Meds"]
    assert scheduler.skipped[0]["description"] == "Walk"


def test_anchor_before_day_start_is_still_honored():
    owner = owner_with(Task("Meds", 10, fixed_time="06:00"), day_start="08:00")

    assert times(Scheduler(owner).build_plan()) == ["06:00"]


# --- multiple pets -----------------------------------------------------------

def two_pet_owner(**kwargs):
    kwargs.setdefault("available_minutes", 240)
    return Owner(
        "Jordan",
        pets=[
            Pet("Mochi", species="cat", tasks=[Task("Litter box", 10, priority="medium")]),
            Pet("Biscuit", species="dog", tasks=[Task("Meds", 5, priority="high")]),
        ],
        **kwargs,
    )


def test_plan_spans_every_pet_and_labels_each_slot():
    plan = Scheduler(two_pet_owner()).build_plan()

    assert [(s["pet"], s["description"]) for s in plan] == [
        ("Biscuit", "Meds"),
        ("Mochi", "Litter box"),
    ]


def test_priority_beats_pet_order_when_the_budget_is_tight():
    # Biscuit's high-priority meds win over Mochi's medium task, even though
    # Mochi is the first pet on the owner.
    owner = two_pet_owner(available_minutes=5)
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan()

    assert [(s["pet"], s["description"]) for s in plan] == [("Biscuit", "Meds")]
    assert scheduler.skipped[0]["pet"] == "Mochi"


def test_tasks_for_filters_the_plan_by_pet():
    scheduler = Scheduler(two_pet_owner())
    scheduler.build_plan()

    assert descriptions(scheduler.tasks_for("Mochi")) == ["Litter box"]
    assert descriptions(scheduler.tasks_for("Biscuit")) == ["Meds"]
    assert scheduler.tasks_for("Nobody") == []


def test_owner_with_no_pets_produces_an_empty_plan():
    scheduler = Scheduler(Owner("Jordan"))

    assert scheduler.build_plan() == []
    assert any("no pets" in line.lower() for line in scheduler.explain())


# --- completion status -------------------------------------------------------


def test_completed_tasks_are_left_out_of_the_plan():
    done = Task("Feed", 10, priority="high")
    done.mark_complete()
    owner = owner_with(done, Task("Walk", 30, priority="low"))
    scheduler = Scheduler(owner)

    assert descriptions(scheduler.build_plan()) == ["Walk"]
    # Left out, not "skipped" — nothing went wrong, it is simply already done.
    assert scheduler.skipped == []


def test_completed_tasks_do_not_consume_the_budget():
    done = Task("Hike", 200, priority="high")
    done.mark_complete()
    owner = owner_with(done, Task("Walk", 30, priority="high"), available_minutes=60)

    assert descriptions(Scheduler(owner).build_plan()) == ["Walk"]


def test_explain_names_the_tasks_that_were_already_done():
    done = Task("Feed", 10)
    done.mark_complete()
    scheduler = Scheduler(owner_with(done, Task("Walk", 30)))
    scheduler.build_plan()
    text = "\n".join(scheduler.explain())

    assert "Already done" in text
    assert "Feed" in text


# --- owner preferences -------------------------------------------------------


def test_skip_low_priority_preference_drops_low_tasks_even_with_spare_time():
    owner = owner_with(
        Task("Meds", 5, priority="high"),
        Task("Brush", 5, priority="low"),
        skip_low_priority=True,
    )
    scheduler = Scheduler(owner)

    assert descriptions(scheduler.build_plan()) == ["Meds"]
    assert scheduler.skipped[0]["description"] == "Brush"
    assert "low-priority" in scheduler.skipped[0]["reason"]


def test_explain_notes_a_preferred_window_match():
    owner = owner_with(
        Task("Walk", 20, priority="high", preferred_time="morning"),
        preferred_times=["morning"],
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    assert "preferred window" in scheduler.scheduled[0]["reason"]


def test_anchored_slots_are_explained_as_pinned():
    scheduler = Scheduler(owner_with(Task("Meds", 10, fixed_time="09:00")))
    scheduler.build_plan()

    assert scheduler.scheduled[0]["anchored"] is True
    assert "pinned to 09:00" in scheduler.scheduled[0]["reason"]


# --- explanation and object contract -----------------------------------------


def test_empty_task_list_produces_an_empty_plan():
    scheduler = Scheduler(Owner("Jordan", pets=[Pet("Mochi")]))

    assert scheduler.build_plan() == []
    assert scheduler.skipped == []
    assert any("no care tasks" in line.lower() for line in scheduler.explain())


def test_explain_mentions_every_scheduled_and_skipped_task():
    owner = owner_with(
        Task("Feed", 10, priority="high"),
        Task("Hike", 90, priority="low"),
        available_minutes=30,
    )
    scheduler = Scheduler(owner)
    scheduler.build_plan()
    text = "\n".join(scheduler.explain())

    assert "Feed" in text
    assert "Hike" in text


def test_explain_before_build_plan_says_so():
    # "No tasks could be scheduled" would be misleading: nothing was attempted.
    scheduler = Scheduler(owner_with(Task("Walk", 20)))
    text = "\n".join(scheduler.explain())

    assert "build_plan" in text
    assert "No tasks could be scheduled" not in text


def test_build_plan_is_repeatable():
    scheduler = Scheduler(
        owner_with(
            Task("Walk", 30, priority="high"),
            Task("Feed", 10, priority="high"),
            available_minutes=60,
        )
    )

    assert descriptions(scheduler.build_plan()) == descriptions(scheduler.build_plan())
    assert len(scheduler.scheduled) == 2


def test_results_cannot_be_passed_into_the_constructor():
    # scheduled/skipped are derived state, not inputs.
    with pytest.raises(TypeError):
        Scheduler(Owner("Jordan"), scheduled=[{"description": "fake"}])


def test_scheduler_rejects_wrong_types():
    with pytest.raises(TypeError):
        Scheduler("Jordan")
    with pytest.raises(TypeError):
        Scheduler(Pet("Mochi"))
