"""Tests for the data classes: Task, Pet, and Owner."""

import pytest

from pawpal_system import Owner, Pet, Task


# --- Task --------------------------------------------------------------------


def test_priority_score_ranks_high_above_medium_above_low():
    assert Task("Meds", 5, priority="high").priority_score() == 3
    assert Task("Walk", 5, priority="medium").priority_score() == 2
    assert Task("Brush", 5, priority="low").priority_score() == 1


def test_sort_key_orders_by_priority_then_duration_then_description():
    long_high = Task("Walk", 30, priority="high")
    short_high = Task("Feed", 10, priority="high")
    medium = Task("Play", 5, priority="medium")

    ordered = sorted([medium, long_high, short_high], key=lambda t: t.sort_key())

    assert [t.description for t in ordered] == ["Feed", "Walk", "Play"]


def test_sort_key_breaks_exact_ties_by_description():
    b = Task("Brush", 10, priority="high")
    a = Task("Almond butter kong", 10, priority="high")

    ordered = sorted([b, a], key=lambda t: t.sort_key())

    assert [t.description for t in ordered] == ["Almond butter kong", "Brush"]


def test_a_task_is_anchored_only_when_it_has_a_fixed_time():
    assert Task("Meds", 5, fixed_time="08:00").is_anchored() is True
    assert Task("Meds", 5, fixed_time="08:00").start_minutes() == 480
    assert Task("Walk", 30).is_anchored() is False
    assert Task("Walk", 30).start_minutes() is None


def test_completion_status_toggles():
    task = Task("Walk", 30)

    assert task.completed is False
    assert task.mark_complete().completed is True
    assert task.mark_incomplete().completed is False


@pytest.mark.parametrize("bad_duration", [0, -10])
def test_non_positive_duration_is_rejected(bad_duration):
    with pytest.raises(ValueError):
        Task("Walk", bad_duration)


def test_bool_is_not_accepted_as_a_duration():
    # bool subclasses int, so True would silently become a 1-minute task.
    with pytest.raises(ValueError):
        Task("Walk", True)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"priority": "urgent"},
        {"preferred_time": "midnight"},
        {"frequency": "every third tuesday"},
        {"fixed_time": "8am"},
        {"fixed_time": "25:00"},
    ],
)
def test_unknown_field_values_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Task("Walk", 20, **kwargs)


def test_empty_description_is_rejected():
    with pytest.raises(ValueError):
        Task("   ", 20)


# --- Pet ---------------------------------------------------------------------


def test_pet_owns_and_totals_its_tasks():
    pet = Pet("Mochi", species="dog")
    pet.add_task(Task("Walk", 30, category="walk"))
    pet.add_task(Task("Feed", 10, category="feeding"))

    assert pet.total_task_minutes() == 40
    assert [t.description for t in pet.tasks_by_category("walk")] == ["Walk"]
    assert pet.remove_task("Walk") is True
    assert pet.remove_task("Walk") is False
    assert pet.total_task_minutes() == 10


def test_pet_separates_pending_from_completed():
    pet = Pet("Mochi", tasks=[Task("Walk", 30), Task("Feed", 10)])
    pet.tasks[1].mark_complete()

    assert [t.description for t in pet.pending_tasks()] == ["Walk"]
    assert [t.description for t in pet.completed_tasks()] == ["Feed"]
    assert pet.pending_minutes() == 30
    assert pet.total_task_minutes() == 40


def test_pet_constructor_rejects_non_tasks():
    # Must match the type check add_task() already applies.
    with pytest.raises(TypeError):
        Pet("Mochi", tasks=["Morning walk"])


# --- Owner -------------------------------------------------------------------


def test_owner_manages_multiple_pets():
    owner = Owner("Jordan")
    owner.add_pet(Pet("Mochi"))
    owner.add_pet(Pet("Biscuit"))

    assert [p.name for p in owner.pets] == ["Mochi", "Biscuit"]
    assert owner.get_pet("Biscuit").name == "Biscuit"
    assert owner.get_pet("Nobody") is None
    assert owner.remove_pet("Mochi") is True
    assert owner.remove_pet("Mochi") is False
    assert [p.name for p in owner.pets] == ["Biscuit"]


def test_owner_rejects_two_pets_with_the_same_name():
    owner = Owner("Jordan", pets=[Pet("Mochi")])

    with pytest.raises(ValueError):
        owner.add_pet(Pet("Mochi"))


def test_owner_constructor_rejects_non_pets():
    with pytest.raises(TypeError):
        Owner("Jordan", pets=["Mochi"])


def test_all_tasks_spans_every_pet_and_names_the_owner_of_each():
    owner = Owner(
        "Jordan",
        pets=[
            Pet("Mochi", tasks=[Task("Walk", 30)]),
            Pet("Biscuit", tasks=[Task("Meds", 5), Task("Feed", 10)]),
        ],
    )

    pairs = owner.all_tasks()

    assert [(p.name, t.description) for p, t in pairs] == [
        ("Mochi", "Walk"),
        ("Biscuit", "Meds"),
        ("Biscuit", "Feed"),
    ]
    assert owner.total_task_minutes() == 45


def test_owner_pending_tasks_excludes_completed_ones_across_pets():
    mochi = Pet("Mochi", tasks=[Task("Walk", 30)])
    biscuit = Pet("Biscuit", tasks=[Task("Meds", 5)])
    biscuit.tasks[0].mark_complete()
    owner = Owner("Jordan", pets=[mochi, biscuit])

    assert [t.description for _, t in owner.pending_tasks()] == ["Walk"]
    assert [t.description for _, t in owner.completed_tasks()] == ["Meds"]
    assert owner.pending_minutes() == 30


def test_owner_knows_when_it_is_overcommitted():
    owner = Owner("Jordan", available_minutes=30)
    owner.add_pet(Pet("Mochi", tasks=[Task("Walk", 60)]))

    assert owner.is_overcommitted() is True
    owner.pets[0].tasks[0].mark_complete()
    assert owner.is_overcommitted() is False


def test_owner_prefers_only_matching_windows():
    owner = Owner("Jordan", preferred_times=["morning"])

    assert owner.prefers(Task("Walk", 30, preferred_time="morning")) is True
    assert owner.prefers(Task("Walk", 30, preferred_time="evening")) is False
    # "any" never counts as a preference match
    assert owner.prefers(Task("Walk", 30, preferred_time="any")) is False


def test_owner_rejects_malformed_day_start():
    with pytest.raises(ValueError):
        Owner("Jordan", day_start="8am")
