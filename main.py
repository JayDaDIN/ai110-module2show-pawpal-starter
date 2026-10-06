"""PawPal+ command-line demo.

Builds a sample owner with two pets and deliberately adds their tasks **out of
chronological order**, so the schedule below is evidence that the scheduler
sorts rather than echoing input order. Two tasks are pinned to the same time on
purpose to show conflict detection warning instead of crashing.

Run it with:

    python main.py
"""

import sys

from pawpal_system import Owner, Pet, Scheduler, Task

WIDTH = 66


def build_demo_owner():
    """A busy owner, two pets, and a day that does not quite fit."""
    biscuit = Pet(
        name="Biscuit",
        species="dog",
        breed="Golden Retriever",
        energy_level="high",
    )
    mochi = Pet(name="Mochi", species="cat", breed="Tabby", energy_level="medium")

    # Added deliberately out of order: 18:00 before 07:30, evening before
    # morning. Nothing here is sorted by hand.
    mochi.add_task(
        Task(
            "Play session",
            duration_minutes=20,
            priority="medium",
            category="enrichment",
            fixed_time="18:00",
            preferred_time="evening",
        )
    )
    biscuit.add_task(
        Task(
            "Grooming",
            duration_minutes=45,
            priority="low",
            category="grooming",
            frequency="weekly",
        )
    )
    biscuit.add_task(
        Task(
            "Heartworm meds",
            duration_minutes=5,
            priority="high",
            category="meds",
            fixed_time="08:00",
            frequency="daily",
        )
    )
    mochi.add_task(
        Task("Litter box", duration_minutes=10, priority="medium", category="other")
    )
    biscuit.add_task(
        Task(
            "Morning walk",
            duration_minutes=30,
            priority="high",
            category="walk",
            preferred_time="morning",
        )
    )
    mochi.add_task(
        Task(
            "Feeding",
            duration_minutes=10,
            priority="high",
            category="feeding",
            fixed_time="07:30",
        )
    )
    # CLASH ON PURPOSE: Biscuit's breakfast is pinned to 07:35, which lands in
    # the middle of Mochi's 07:30-07:40 feeding. One owner cannot be in two
    # places, so the scheduler should warn rather than silently double-book.
    biscuit.add_task(
        Task(
            "Breakfast",
            duration_minutes=10,
            priority="medium",
            category="feeding",
            fixed_time="07:35",
        )
    )

    return Owner(
        name="Jordan",
        available_minutes=100,
        day_start="07:30",
        preferred_times=["morning", "evening"],
        pets=[mochi, biscuit],
    )


def rule(char="="):
    """Print a horizontal divider across the report width."""
    print(char * WIDTH)


def print_header(owner):
    """Print the owner, budget, pets and how much work is outstanding."""
    rule()
    print("  PawPal+ - Today's Schedule".center(WIDTH).rstrip())
    rule()
    print(f"  Owner:  {owner.name}")
    print(f"  Budget: {owner.available_minutes} min, starting {owner.day_start}")
    pets = ", ".join(f"{p.name} ({p.species})" for p in owner.pets)
    print(f"  Pets:   {pets}")
    print(f"  To do:  {owner.pending_minutes()} min of pending work")
    if owner.is_overcommitted():
        over = owner.pending_minutes() - owner.available_minutes
        print(f"          ({over} min more than the day allows)")


def print_plan(scheduler):
    """Print the finished schedule as a time-ordered table."""
    rule("-")
    print(f"  {'TIME':<7}{'PET':<10}{'TASK':<24}{'MINS':>5}  {'PRIORITY':<8}")
    rule("-")

    if not scheduler.scheduled:
        print("  Nothing could be scheduled today.")
        return

    for slot in scheduler.scheduled:
        pin = "*" if slot["anchored"] else " "
        print(
            f"{pin} {slot['start_time']:<7}{slot['pet']:<10}"
            f"{slot['description']:<24}{slot['duration_minutes']:>5}  "
            f"{slot['priority']:<8}"
        )

    rule("-")
    print(
        f"  {len(scheduler.scheduled)} task(s), "
        f"{scheduler.total_scheduled_minutes()} of "
        f"{scheduler.owner.available_minutes} minutes used."
    )
    print("  * = pinned to a fixed time")


def print_skipped(scheduler):
    """Print everything that did not make the plan, with its reason."""
    if not scheduler.skipped:
        return
    print()
    print("  NOT TODAY")
    rule("-")
    for item in scheduler.skipped:
        print(f"  {item['description']} ({item['pet']})")
        print(f"    reason: {item['reason']}")


def print_per_pet(scheduler):
    """Break the single shared timeline back down by animal."""
    print()
    print("  BY PET")
    rule("-")
    for pet in scheduler.owner.pets:
        slots = scheduler.tasks_for(pet.name)
        minutes = sum(s["duration_minutes"] for s in slots)
        print(f"  {pet.name} ({pet.breed}) - {len(slots)} task(s), {minutes} min")
        for slot in slots:
            print(f"    {slot['start_time']}  {slot['description']}")
        done = pet.completed_tasks()
        if done:
            already = ", ".join(t.description for t in done)
            print(f"    already done: {already}")


def print_reasoning(scheduler):
    """Print the scheduler's own account of why it chose this plan."""
    print()
    print("  WHY THIS PLAN")
    rule("-")
    for line in scheduler.explain():
        print(f"  {line}")


def print_entry_order(owner):
    """Show the order tasks were typed in, next to clock order."""
    print()
    print("  AS ENTERED (deliberately out of order)")
    rule("-")
    for pet, task in owner.all_tasks():
        when = task.fixed_time or "flexible"
        print(f"  {when:<9} {pet.name:<9} {task.description}")


def print_time_order(scheduler):
    """Scheduler.sort_by_time() puts the same tasks on a clock."""
    print()
    print("  SORTED BY TIME  (Scheduler.sort_by_time)")
    rule("-")
    for pet, task in scheduler.sort_by_time():
        when = task.fixed_time or "flexible"
        print(f"  {when:<9} {pet.name:<9} {task.description}")


def print_conflicts(scheduler):
    """Conflict detection warns; it never raises."""
    print()
    print("  CONFLICT CHECK  (Scheduler.conflict_warnings)")
    rule("-")
    warnings = scheduler.conflict_warnings()
    if not warnings:
        print("  No clashes: nothing is double-booked.")
        return
    for warning in warnings:
        print(f"  {warning}")
    print(f"  ({len(warnings)} warning(s) — the program keeps running.)")


def print_filters(scheduler):
    """Filtering by pet name and by completion status."""
    print()
    print("  FILTERS  (Scheduler.filter_tasks)")
    rule("-")
    for pet in scheduler.owner.pets:
        names = [t.description for _, t in scheduler.filter_tasks(pet=pet.name)]
        print(f"  pet={pet.name:<9} {', '.join(names)}")
    for status in ("pending", "done"):
        names = [t.description for _, t in scheduler.filter_tasks(status=status)]
        print(f"  status={status:<6} {', '.join(names) if names else '(none)'}")


def print_recurrence(owner, scheduler):
    """Completing a repeating task queues a brand new instance for next time."""
    print()
    print("  RECURRENCE  (Pet.complete_task)")
    rule("-")
    mochi = owner.get_pet("Mochi")
    before = len(mochi.tasks)
    successor = mochi.complete_task("Feeding", on=scheduler.plan_date)
    print(f"  Ticked off 'Feeding' for Mochi on {scheduler.plan_date:%a %d %b}.")
    print(f"  Mochi's task count: {before} -> {len(mochi.tasks)}")
    print(
        f"  New instance queued: '{successor.description}' "
        f"({successor.repeat_text()}) due {successor.due_date:%a %d %b}, "
        f"completed={successor.completed}"
    )

    tomorrow = scheduler.plan_date.replace() + (successor.due_date - scheduler.plan_date)
    scheduler.build_plan(on_date=tomorrow)
    feedings = [s for s in scheduler.scheduled if s["description"] == "Feeding"]
    print(
        f"  Plan for {tomorrow:%a %d %b} contains {len(feedings)} 'Feeding' "
        f"(the successor, not a duplicate)."
    )


def main():
    """Build the demo owner, plan the day, and print every section."""
    # The schedule uses a few non-ASCII characters; make sure they survive
    # being piped to a file or a narrow Windows console.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    owner = build_demo_owner()
    scheduler = Scheduler(owner)
    scheduler.build_plan()

    print_header(owner)
    print_entry_order(owner)
    print_time_order(scheduler)
    print_conflicts(scheduler)
    print()
    print("  TODAY'S SCHEDULE")
    print_plan(scheduler)
    print_skipped(scheduler)
    print_per_pet(scheduler)
    print_filters(scheduler)
    print_reasoning(scheduler)
    # Last, because completing a task mutates the owner: it retires Mochi's
    # feeding and queues tomorrow's, which would change everything above.
    print_recurrence(owner, scheduler)
    rule()


if __name__ == "__main__":
    main()
