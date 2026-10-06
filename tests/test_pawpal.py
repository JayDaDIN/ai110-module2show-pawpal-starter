"""Two core behavior tests for PawPal+."""

from pawpal_system import Pet, Task


def test_mark_complete_changes_the_task_status():
    """Task completion: mark_complete() flips completed from False to True."""
    task = Task("Morning walk", duration_minutes=30)

    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_adding_a_task_increases_the_pets_task_count():
    """Task addition: add_task() grows the pet's task list by one."""
    pet = Pet("Mochi", species="cat")

    assert len(pet.tasks) == 0

    pet.add_task(Task("Feeding", duration_minutes=10))

    assert len(pet.tasks) == 1

    pet.add_task(Task("Litter box", duration_minutes=10))

    assert len(pet.tasks) == 2
