"""PawPal+ logic layer.

All four backend classes live here, separate from the Streamlit UI in app.py:

    Task      - one activity: description, time, frequency, completion status
    Pet       - pet details plus the list of tasks belonging to that pet
    Owner     - manages multiple pets and exposes all of their tasks
    Scheduler - the brain: retrieves, organizes and plans tasks across pets

Relationships: an Owner owns its Pets and a Pet owns its Tasks (both
composition); a Scheduler reads from an Owner but owns nothing. See
diagrams/uml.mmd.
"""

from dataclasses import dataclass, field

PRIORITY_SCORES = {"high": 3, "medium": 2, "low": 1}

TIMES_OF_DAY = ("morning", "afternoon", "evening", "any")

FREQUENCIES = ("daily", "weekly")

MINUTES_IN_DAY = 24 * 60


def _to_minutes(value):
    """Turn "08:30" into 510, the number of minutes since midnight."""
    try:
        hours, minutes = str(value).split(":")
        hours, minutes = int(hours), int(minutes)
    except (ValueError, AttributeError):
        raise ValueError(f"time must look like 'HH:MM', got {value!r}")
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError(f"time out of range: {value!r}")
    return hours * 60 + minutes


def _to_clock(total_minutes):
    """Turn 510 back into "08:30". Wraps at midnight."""
    total_minutes %= MINUTES_IN_DAY
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


# --- Core action 1: track pet care tasks -------------------------------------


@dataclass
class Task:
    """A single pet care activity.

    `duration_minutes` is how long it takes. `fixed_time` is optional: set it
    to an "HH:MM" string to anchor the task to that exact time, or leave it
    None to let the Scheduler decide when the task happens.
    """

    description: str
    duration_minutes: int
    priority: str = "medium"
    category: str = "other"
    fixed_time: str = None
    preferred_time: str = "any"
    frequency: str = "daily"
    completed: bool = False

    def __post_init__(self):
        """Validate every field and tidy the description, right after __init__."""
        if not self.description or not str(self.description).strip():
            raise ValueError("description cannot be empty")
        # bool is a subclass of int, so True would otherwise pass as 1 minute.
        if isinstance(self.duration_minutes, bool) or not isinstance(
            self.duration_minutes, int
        ):
            raise ValueError("duration_minutes must be a positive whole number")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be a positive whole number")
        if self.priority not in PRIORITY_SCORES:
            raise ValueError(
                f"priority must be one of {sorted(PRIORITY_SCORES)}, got {self.priority!r}"
            )
        if self.preferred_time not in TIMES_OF_DAY:
            raise ValueError(
                f"preferred_time must be one of {list(TIMES_OF_DAY)}, "
                f"got {self.preferred_time!r}"
            )
        if self.frequency not in FREQUENCIES:
            raise ValueError(
                f"frequency must be one of {list(FREQUENCIES)}, got {self.frequency!r}"
            )
        if self.fixed_time is not None:
            _to_minutes(self.fixed_time)  # validates the format, raises if malformed
        self.description = self.description.strip()

    def priority_score(self):
        """Numeric rank for this task's priority. Higher is more important."""
        return PRIORITY_SCORES[self.priority]

    def sort_key(self):
        """Ordering the scheduler uses for flexible (non-anchored) tasks.

        Highest priority first, then the shortest task, then description so
        that the resulting plan is deterministic and therefore testable.
        """
        return (-self.priority_score(), self.duration_minutes, self.description)

    def is_anchored(self):
        """True when the owner pinned this task to a specific clock time."""
        return self.fixed_time is not None

    def start_minutes(self):
        """The anchored start time in minutes since midnight, or None."""
        return _to_minutes(self.fixed_time) if self.is_anchored() else None

    def mark_complete(self):
        """Tick this task off; completed tasks are left out of the plan."""
        self.completed = True
        return self

    def mark_incomplete(self):
        """Put this task back on the to-do list so it gets planned again."""
        self.completed = False
        return self


@dataclass
class Pet:
    """Pet details plus the tasks that belong to this pet."""

    name: str
    species: str = "dog"
    breed: str = ""
    energy_level: str = "medium"
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self):
        """Validate the name and type-check any tasks passed to the constructor."""
        if not self.name or not str(self.name).strip():
            raise ValueError("name cannot be empty")
        self.name = self.name.strip()
        # Route the constructor through add_task so tasks passed in are held to
        # the same type check as tasks added later.
        incoming, self.tasks = list(self.tasks), []
        for task in incoming:
            self.add_task(task)

    def add_task(self, task):
        """Give this pet one more task to do, and return it."""
        if not isinstance(task, Task):
            raise TypeError("add_task expects a Task")
        self.tasks.append(task)
        return task

    def remove_task(self, description):
        """Remove the first task with this description. True if one was removed."""
        for i, task in enumerate(self.tasks):
            if task.description == description:
                del self.tasks[i]
                return True
        return False

    def tasks_by_category(self, category):
        """This pet's tasks in one category, such as "meds" or "walk"."""
        return [t for t in self.tasks if t.category == category]

    def pending_tasks(self):
        """Tasks still to be done today."""
        return [t for t in self.tasks if not t.completed]

    def completed_tasks(self):
        """Tasks already ticked off today."""
        return [t for t in self.tasks if t.completed]

    def total_task_minutes(self):
        """Minutes of work across every task, done or not."""
        return sum(t.duration_minutes for t in self.tasks)

    def pending_minutes(self):
        """Minutes of work still left to do for this pet."""
        return sum(t.duration_minutes for t in self.pending_tasks())


# --- Core action 2: consider constraints, across every pet -------------------


@dataclass
class Owner:
    """The person doing the care.

    Manages multiple pets and holds every constraint the Scheduler reads. The
    time budget is a single shared pool: all pets' tasks compete for the same
    `available_minutes`, so the scheduler trades off across pets.
    """

    name: str
    available_minutes: int = 120
    day_start: str = "08:00"
    preferred_times: list[str] = field(default_factory=list)
    skip_low_priority: bool = False
    pets: list[Pet] = field(default_factory=list)

    def __post_init__(self):
        """Validate the name, budget and start time, and type-check any pets."""
        # Each setter owns its own validation, so the constructor reuses them
        # rather than repeating the same checks.
        self.rename(self.name)
        self.set_available_minutes(self.available_minutes)
        self.set_day_start(self.day_start)
        self.preferred_times = list(self.preferred_times)
        incoming, self.pets = list(self.pets), []
        for pet in incoming:
            self.add_pet(pet)

    # -- validated setters, so the UI can edit a live Owner safely --------

    def rename(self, name):
        """Change the owner's name, rejecting an empty one."""
        if not name or not str(name).strip():
            raise ValueError("name cannot be empty")
        self.name = str(name).strip()
        return self.name

    def set_available_minutes(self, minutes):
        """Set today's shared time budget, rejecting negatives and non-integers."""
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise ValueError("available_minutes must be zero or a positive whole number")
        if minutes < 0:
            raise ValueError("available_minutes must be zero or a positive whole number")
        self.available_minutes = minutes
        return self.available_minutes

    def set_day_start(self, value):
        """Set the time the day begins, rejecting anything not "HH:MM"."""
        _to_minutes(value)  # validates the format, raises if malformed
        self.day_start = value
        return self.day_start

    # -- managing pets --------------------------------------------------

    def add_pet(self, pet):
        """Put one more pet in this owner's care, and return it."""
        if not isinstance(pet, Pet):
            raise TypeError("add_pet expects a Pet")
        if self.get_pet(pet.name) is not None:
            raise ValueError(f"this owner already has a pet named {pet.name!r}")
        self.pets.append(pet)
        return pet

    def remove_pet(self, name):
        """Remove the pet with this name. True if one was removed."""
        for i, pet in enumerate(self.pets):
            if pet.name == name:
                del self.pets[i]
                return True
        return False

    def get_pet(self, name):
        """The pet with this name, or None."""
        for pet in self.pets:
            if pet.name == name:
                return pet
        return None

    # -- access to every pet's tasks -------------------------------------

    def all_tasks(self):
        """Every task across every pet, as (pet, task) pairs.

        Pairs rather than bare tasks because a plan spanning several pets has
        to be able to say which pet each task belongs to.
        """
        return [(pet, task) for pet in self.pets for task in pet.tasks]

    def pending_tasks(self):
        """Every not-yet-completed task across every pet, as (pet, task) pairs."""
        return [(pet, task) for pet, task in self.all_tasks() if not task.completed]

    def completed_tasks(self):
        """Every already-done task across every pet, as (pet, task) pairs."""
        return [(pet, task) for pet, task in self.all_tasks() if task.completed]

    def total_task_minutes(self):
        """Minutes of work across every pet, done or not."""
        return sum(task.duration_minutes for _, task in self.all_tasks())

    def pending_minutes(self):
        """Minutes of work still left to do across every pet."""
        return sum(task.duration_minutes for _, task in self.pending_tasks())

    # -- constraints the scheduler asks about -----------------------------

    def has_capacity_for(self, minutes_used, task):
        """Can this task still fit in the day's remaining budget?"""
        return minutes_used + task.duration_minutes <= self.available_minutes

    def minutes_remaining(self, minutes_used):
        """How much of the day's budget is still unspent, never below zero."""
        return max(0, self.available_minutes - minutes_used)

    def prefers(self, task):
        """Does this task land in one of the owner's preferred windows?"""
        if not self.preferred_times or task.preferred_time == "any":
            return False
        return task.preferred_time in self.preferred_times

    def is_overcommitted(self):
        """More pending work than there are minutes to do it in."""
        return self.pending_minutes() > self.available_minutes


# --- Core action 3: produce a daily plan and explain it ----------------------


@dataclass
class Scheduler:
    """The brain. Retrieves, organizes and plans tasks across all of an owner's pets.

    Strategy, in order:

    1. Drop completed tasks, and low-priority ones if the owner asked.
    2. Place anchored tasks (those with a `fixed_time`) at their exact times.
       Where two anchors overlap, the earlier one wins.
    3. Fill the gaps around those anchors with the remaining flexible tasks,
       highest priority first, shortest first on ties.
    4. Stop adding work once the owner's shared time budget is exhausted.
    """

    owner: Owner
    # Results of build_plan(), not inputs — init=False keeps them out of the
    # generated __init__ so they cannot be passed in from outside.
    scheduled: list[dict] = field(default_factory=list, init=False)
    skipped: list[dict] = field(default_factory=list, init=False)
    planned: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        """Reject anything that is not a real Owner before planning starts."""
        if not isinstance(self.owner, Owner):
            raise TypeError("Scheduler expects an Owner")

    # -- the plan ---------------------------------------------------------

    def build_plan(self):
        """Choose and order today's tasks across every pet.

        Returns the list of scheduled slots, each a dict with `start_time`,
        `pet`, `description`, `duration_minutes`, `priority`, `category`,
        `anchored` and `reason`.
        """
        self.scheduled = []
        self.skipped = []
        self.planned = True

        anchored, flexible = self._gather()
        placements, minutes_used = self._place_anchored(anchored)
        placements += self._place_flexible(flexible, placements, minutes_used)

        placements.sort(key=lambda p: p["start"])
        self.scheduled = [
            {
                "start_time": _to_clock(p["start"]),
                "pet": p["pet"].name,
                "description": p["task"].description,
                "category": p["task"].category,
                "duration_minutes": p["task"].duration_minutes,
                "priority": p["task"].priority,
                "anchored": p["task"].is_anchored(),
                "reason": self._reason_for(p["task"]),
            }
            for p in placements
        ]
        return self.scheduled

    def _gather(self):
        """Collect this owner's plannable tasks, split into anchored and flexible."""
        anchored, flexible = [], []

        for pet, task in self.owner.all_tasks():
            if task.completed:
                continue  # already done; nothing to plan
            if self.owner.skip_low_priority and task.priority == "low":
                self._skip(pet, task, f"{self.owner.name} chose to skip low-priority tasks today")
                continue
            (anchored if task.is_anchored() else flexible).append((pet, task))

        # Anchors are placed in clock order; the sort_key tie-break keeps two
        # anchors at the same minute in a deterministic order.
        anchored.sort(key=lambda pair: (pair[1].start_minutes(), pair[1].sort_key()))
        flexible.sort(key=lambda pair: pair[1].sort_key())
        return anchored, flexible

    def _place_anchored(self, anchored):
        """Pin each anchored task to its fixed time. Earlier anchors win collisions."""
        placements = []
        minutes_used = 0
        busy_until = None

        for pet, task in anchored:
            start = task.start_minutes()

            if busy_until is not None and start < busy_until:
                self._skip(
                    pet,
                    task,
                    f"its fixed time {task.fixed_time} overlaps a task already "
                    f"running until {_to_clock(busy_until)}",
                )
                continue

            if not self.owner.has_capacity_for(minutes_used, task):
                self._skip(pet, task, self._no_time_reason(task, minutes_used))
                continue

            placements.append({"start": start, "pet": pet, "task": task})
            minutes_used += task.duration_minutes
            busy_until = start + task.duration_minutes

        return placements, minutes_used

    def _place_flexible(self, flexible, anchored_placements, minutes_used):
        """Fit the unanchored tasks into the gaps left between the anchors."""
        gaps = self._build_gaps(anchored_placements)
        placements = []

        for pet, task in flexible:
            if not self.owner.has_capacity_for(minutes_used, task):
                self._skip(pet, task, self._no_time_reason(task, minutes_used))
                continue

            slot = self._first_gap_that_fits(gaps, task.duration_minutes)
            if slot is None:
                self._skip(
                    pet,
                    task,
                    f"no {task.duration_minutes} min gap left between the "
                    f"fixed-time tasks",
                )
                continue

            index, (start, end) = slot
            placements.append({"start": start, "pet": pet, "task": task})
            gaps[index] = (start + task.duration_minutes, end)
            minutes_used += task.duration_minutes

        return placements

    def _build_gaps(self, placements):
        """The free stretches of the day, given the anchored tasks already placed."""
        day_start = _to_minutes(self.owner.day_start)
        if not placements:
            return [(day_start, MINUTES_IN_DAY)]

        gaps = []
        cursor = day_start
        for placement in sorted(placements, key=lambda p: p["start"]):
            start = placement["start"]
            if start > cursor:
                gaps.append((cursor, start))
            cursor = max(cursor, start + placement["task"].duration_minutes)
        gaps.append((cursor, MINUTES_IN_DAY))
        return gaps

    @staticmethod
    def _first_gap_that_fits(gaps, duration):
        """The earliest gap with room for this many minutes, or None."""
        for index, (start, end) in enumerate(gaps):
            if end - start >= duration:
                return index, (start, end)
        return None

    # -- explanation -------------------------------------------------------

    def explain(self):
        """Human-readable reasoning for the plan that build_plan() produced."""
        lines = [
            f"Strategy: fixed-time tasks first, then the rest by highest priority "
            f"and shortest duration, all sharing {self.owner.name}'s "
            f"{self.owner.available_minutes} min from {self.owner.day_start}."
        ]

        if not self.planned:
            lines.append("No plan has been built yet — call build_plan() first.")
            return lines

        pet_names = ", ".join(pet.name for pet in self.owner.pets)
        lines.append(
            f"Pets: {pet_names}." if self.owner.pets else "This owner has no pets yet."
        )

        if not self.owner.all_tasks():
            lines.append("No care tasks were entered, so the plan is empty.")
            return lines

        done = self.owner.completed_tasks()
        if done:
            lines.append(
                f"Already done, so left out of the plan: "
                + ", ".join(f"{t.description} ({p.name})" for p, t in done)
                + "."
            )

        if self.scheduled:
            lines.append(
                f"Scheduled {len(self.scheduled)} task(s), using "
                f"{self.total_scheduled_minutes()} of "
                f"{self.owner.available_minutes} available minutes:"
            )
            for slot in self.scheduled:
                lines.append(
                    f"  {slot['start_time']} — {slot['description']} for "
                    f"{slot['pet']} ({slot['duration_minutes']} min): {slot['reason']}"
                )
        else:
            lines.append("No tasks could be scheduled today.")

        if self.skipped:
            lines.append(f"Skipped {len(self.skipped)} task(s):")
            for item in self.skipped:
                lines.append(
                    f"  {item['description']} for {item['pet']}: {item['reason']}"
                )

        return lines

    # -- small helpers ------------------------------------------------------

    def total_scheduled_minutes(self):
        """Minutes of work the finished plan actually commits to."""
        return sum(slot["duration_minutes"] for slot in self.scheduled)

    def tasks_for(self, pet_name):
        """The scheduled slots belonging to one pet."""
        return [slot for slot in self.scheduled if slot["pet"] == pet_name]

    def _skip(self, pet, task, reason):
        """Record that this task did not make today's plan, and why."""
        self.skipped.append(
            {
                "pet": pet.name,
                "description": task.description,
                "priority": task.priority,
                "duration_minutes": task.duration_minutes,
                "reason": reason,
            }
        )

    def _no_time_reason(self, task, minutes_used):
        """Word the "ran out of budget" skip message for one task."""
        remaining = self.owner.minutes_remaining(minutes_used)
        return (
            f"needs {task.duration_minutes} min but only {remaining} min of the "
            f"{self.owner.available_minutes} min budget are left"
        )

    def _reason_for(self, task):
        """Say in one phrase why this task earned its place in the plan."""
        if task.is_anchored():
            reason = f"pinned to {task.fixed_time}"
        else:
            reason = f"{task.priority} priority"
        if self.owner.prefers(task):
            reason += f", and {task.preferred_time} matches your preferred window"
        return reason
