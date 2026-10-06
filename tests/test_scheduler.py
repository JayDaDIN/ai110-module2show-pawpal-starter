import pytest

from pawpal_system import CareTask, Owner, Pet, Scheduler


def make_pet(*tasks):
    return Pet("Mochi", species="dog", tasks=list(tasks))


def titles(slots):
    return [slot["title"] for slot in slots]


def test_high_priority_tasks_are_scheduled_first():
    pet = make_pet(
        CareTask("Brush", 10, priority="low"),
        CareTask("Play", 10, priority="medium"),
        CareTask("Meds", 10, priority="high"),
    )
    plan = Scheduler(Owner("Jordan", available_minutes=120), pet).build_plan()

    assert titles(plan) == ["Meds", "Play", "Brush"]


def test_equal_priority_breaks_tie_by_shortest_duration():
    pet = make_pet(
        CareTask("Long walk", 30, priority="high"),
        CareTask("Feeding", 10, priority="high"),
    )
    plan = Scheduler(Owner("Jordan", available_minutes=120), pet).build_plan()

    assert titles(plan) == ["Feeding", "Long walk"]


def test_plan_never_exceeds_the_time_budget():
    pet = make_pet(
        CareTask("Walk", 45, priority="high"),
        CareTask("Groom", 45, priority="medium"),
        CareTask("Train", 45, priority="low"),
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=60), pet)
    scheduler.build_plan()

    assert scheduler.total_scheduled_minutes() <= 60


def test_task_that_does_not_fit_is_skipped_with_a_reason():
    pet = make_pet(CareTask("Long hike", 90, priority="high"))
    scheduler = Scheduler(Owner("Jordan", available_minutes=30), pet)
    plan = scheduler.build_plan()

    assert plan == []
    assert len(scheduler.skipped) == 1
    assert scheduler.skipped[0]["title"] == "Long hike"
    assert "90 min" in scheduler.skipped[0]["reason"]


def test_shorter_task_still_fits_after_a_longer_one_is_skipped():
    # This is the behavior that proves the scheduler continues past a task that
    # does not fit rather than stopping at the first overflow.
    pet = make_pet(
        CareTask("Hike", 50, priority="high"),
        CareTask("Groom", 30, priority="high"),
        CareTask("Feed", 10, priority="high"),
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=60), pet)
    plan = scheduler.build_plan()

    # Sorted shortest-first within "high": Feed (10), Groom (30), Hike (50).
    # Feed and Groom fit in 60 min; Hike does not.
    assert titles(plan) == ["Feed", "Groom"]
    assert [s["title"] for s in scheduler.skipped] == ["Hike"]
    assert scheduler.total_scheduled_minutes() == 40


def test_skip_low_priority_preference_drops_low_tasks_even_with_spare_time():
    pet = make_pet(
        CareTask("Meds", 5, priority="high"),
        CareTask("Brush", 5, priority="low"),
    )
    owner = Owner("Jordan", available_minutes=240, skip_low_priority=True)
    scheduler = Scheduler(owner, pet)
    plan = scheduler.build_plan()

    assert titles(plan) == ["Meds"]
    assert scheduler.skipped[0]["title"] == "Brush"
    assert "low-priority" in scheduler.skipped[0]["reason"]


def test_start_times_advance_by_each_task_duration():
    pet = make_pet(
        CareTask("Feed", 30, priority="high"),
        CareTask("Walk", 45, priority="medium"),
        CareTask("Brush", 15, priority="low"),
    )
    plan = Scheduler(Owner("Jordan", available_minutes=240, day_start="08:00"), pet).build_plan()

    assert [slot["start_time"] for slot in plan] == ["08:00", "08:30", "09:15"]


def test_start_times_cross_the_hour_boundary_correctly():
    pet = make_pet(
        CareTask("Walk", 30, priority="high"),
        CareTask("Feed", 30, priority="medium"),
    )
    plan = Scheduler(Owner("Jordan", available_minutes=240, day_start="08:45"), pet).build_plan()

    assert [slot["start_time"] for slot in plan] == ["08:45", "09:15"]


def test_empty_task_list_produces_an_empty_plan():
    scheduler = Scheduler(Owner("Jordan"), Pet("Mochi"))

    assert scheduler.build_plan() == []
    assert scheduler.skipped == []
    assert any("no care tasks" in line.lower() for line in scheduler.explain())


def test_zero_available_minutes_skips_everything():
    pet = make_pet(CareTask("Feed", 5, priority="high"))
    scheduler = Scheduler(Owner("Jordan", available_minutes=0), pet)

    assert scheduler.build_plan() == []
    assert len(scheduler.skipped) == 1


def test_explain_mentions_every_scheduled_and_skipped_task():
    pet = make_pet(
        CareTask("Feed", 10, priority="high"),
        CareTask("Hike", 90, priority="low"),
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=30), pet)
    scheduler.build_plan()
    text = "\n".join(scheduler.explain())

    assert "Feed" in text
    assert "Hike" in text


def test_explain_notes_a_preferred_window_match():
    pet = make_pet(CareTask("Walk", 20, priority="high", preferred_time="morning"))
    owner = Owner("Jordan", available_minutes=60, preferred_times=["morning"])
    scheduler = Scheduler(owner, pet)
    scheduler.build_plan()

    assert "preferred window" in scheduler.scheduled[0]["reason"]


def test_build_plan_is_repeatable():
    pet = make_pet(
        CareTask("Walk", 30, priority="high"),
        CareTask("Feed", 10, priority="high"),
    )
    scheduler = Scheduler(Owner("Jordan", available_minutes=60), pet)

    assert titles(scheduler.build_plan()) == titles(scheduler.build_plan())
    assert len(scheduler.scheduled) == 2


def test_explain_before_build_plan_says_so():
    # "No tasks could be scheduled" would be misleading: nothing was attempted.
    scheduler = Scheduler(Owner("Jordan"), make_pet(CareTask("Walk", 20)))
    text = "\n".join(scheduler.explain())

    assert "build_plan" in text
    assert "No tasks could be scheduled" not in text


def test_results_cannot_be_passed_into_the_constructor():
    # scheduled/skipped are derived state, not inputs.
    with pytest.raises(TypeError):
        Scheduler(Owner("Jordan"), Pet("Mochi"), scheduled=[{"title": "fake"}])


def test_scheduler_rejects_wrong_types():
    with pytest.raises(TypeError):
        Scheduler("Jordan", Pet("Mochi"))
    with pytest.raises(TypeError):
        Scheduler(Owner("Jordan"), "Mochi")
