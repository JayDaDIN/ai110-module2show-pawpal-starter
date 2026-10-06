import pytest

from pawpal_system import CareTask, Owner, Pet


def test_priority_score_ranks_high_above_medium_above_low():
    high = CareTask("Meds", 5, priority="high")
    medium = CareTask("Walk", 5, priority="medium")
    low = CareTask("Brush", 5, priority="low")

    assert high.priority_score() == 3
    assert medium.priority_score() == 2
    assert low.priority_score() == 1
    assert high.priority_score() > medium.priority_score() > low.priority_score()


def test_sort_key_orders_by_priority_then_duration_then_title():
    long_high = CareTask("Walk", 30, priority="high")
    short_high = CareTask("Feed", 10, priority="high")
    medium = CareTask("Play", 5, priority="medium")

    ordered = sorted([medium, long_high, short_high], key=lambda t: t.sort_key())

    assert [t.title for t in ordered] == ["Feed", "Walk", "Play"]


def test_sort_key_breaks_exact_ties_by_title():
    b = CareTask("Brush", 10, priority="high")
    a = CareTask("Almond butter kong", 10, priority="high")

    ordered = sorted([b, a], key=lambda t: t.sort_key())

    assert [t.title for t in ordered] == ["Almond butter kong", "Brush"]


@pytest.mark.parametrize("bad_duration", [0, -10])
def test_non_positive_duration_is_rejected(bad_duration):
    with pytest.raises(ValueError):
        CareTask("Walk", bad_duration)


def test_unknown_priority_is_rejected():
    with pytest.raises(ValueError):
        CareTask("Walk", 20, priority="urgent")


def test_unknown_preferred_time_is_rejected():
    with pytest.raises(ValueError):
        CareTask("Walk", 20, preferred_time="midnight")


def test_unknown_recurrence_is_rejected():
    with pytest.raises(ValueError):
        CareTask("Walk", 20, recurrence="every third tuesday")


def test_bool_is_not_accepted_as_a_duration():
    # bool subclasses int, so True would silently become a 1-minute task.
    with pytest.raises(ValueError):
        CareTask("Walk", True)


def test_pet_constructor_rejects_non_tasks():
    # Must match the type check add_task() already applies.
    with pytest.raises(TypeError):
        Pet("Mochi", tasks=["Morning walk"])


def test_empty_title_is_rejected():
    with pytest.raises(ValueError):
        CareTask("   ", 20)


def test_pet_owns_and_totals_its_tasks():
    pet = Pet("Mochi", species="dog")
    pet.add_task(CareTask("Walk", 30, category="walk"))
    pet.add_task(CareTask("Feed", 10, category="feeding"))

    assert pet.total_task_minutes() == 40
    assert [t.title for t in pet.tasks_by_category("walk")] == ["Walk"]
    assert pet.remove_task("Walk") is True
    assert pet.remove_task("Walk") is False
    assert pet.total_task_minutes() == 10


def test_owner_prefers_only_matching_windows():
    owner = Owner("Jordan", preferred_times=["morning"])

    assert owner.prefers(CareTask("Walk", 30, preferred_time="morning")) is True
    assert owner.prefers(CareTask("Walk", 30, preferred_time="evening")) is False
    # "any" never counts as a preference match
    assert owner.prefers(CareTask("Walk", 30, preferred_time="any")) is False


def test_owner_rejects_malformed_day_start():
    with pytest.raises(ValueError):
        Owner("Jordan", day_start="8am")
