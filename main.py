"""PawPal+ command-line demo.

Builds a sample owner with two pets, gives them a mix of fixed-time and
flexible tasks, then prints today's schedule and the reasoning behind it.

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
        tasks=[
            # Anchored: the meds have to happen at 08:00 sharp.
            Task(
                "Heartworm meds",
                duration_minutes=5,
                priority="high",
                category="meds",
                fixed_time="08:00",
                frequency="daily",
            ),
            Task(
                "Morning walk",
                duration_minutes=30,
                priority="high",
                category="walk",
                preferred_time="morning",
            ),
            Task(
                "Grooming",
                duration_minutes=45,
                priority="low",
                category="grooming",
                frequency="weekly",
            ),
            # Already done before the planner ran.
            Task(
                "Evening walk",
                duration_minutes=30,
                priority="medium",
                category="walk",
                completed=True,
            ),
        ],
    )

    mochi = Pet(
        name="Mochi",
        species="cat",
        breed="Tabby",
        energy_level="medium",
        tasks=[
            # Anchored: breakfast is the first thing that happens.
            Task(
                "Feeding",
                duration_minutes=10,
                priority="high",
                category="feeding",
                fixed_time="07:30",
            ),
            Task(
                "Litter box",
                duration_minutes=10,
                priority="medium",
                category="other",
            ),
            # Anchored: the evening play session is a standing appointment.
            Task(
                "Play session",
                duration_minutes=20,
                priority="medium",
                category="enrichment",
                fixed_time="18:00",
                preferred_time="evening",
            ),
        ],
    )

    return Owner(
        name="Jordan",
        available_minutes=100,
        day_start="07:30",
        preferred_times=["morning", "evening"],
        pets=[mochi, biscuit],
    )


def rule(char="="):
    print(char * WIDTH)


def print_header(owner):
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
    if not scheduler.skipped:
        return
    print()
    print("  NOT TODAY")
    rule("-")
    for item in scheduler.skipped:
        print(f"  {item['description']} ({item['pet']})")
        print(f"    reason: {item['reason']}")


def print_per_pet(scheduler):
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
    print()
    print("  WHY THIS PLAN")
    rule("-")
    for line in scheduler.explain():
        print(f"  {line}")


def main():
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
    print_plan(scheduler)
    print_skipped(scheduler)
    print_per_pet(scheduler)
    print_reasoning(scheduler)
    rule()


if __name__ == "__main__":
    main()
