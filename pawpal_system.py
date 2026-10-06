"""PawPal+ logic layer.

All four backend classes live here, separate from the Streamlit UI in app.py:

    Task      - one activity: description, time, recurrence, completion status
    Pet       - pet details plus the list of tasks belonging to that pet
    Owner     - manages multiple pets and exposes all of their tasks
    Scheduler - the brain: retrieves, organizes and plans tasks across pets

Relationships: an Owner owns its Pets and a Pet owns its Tasks (both
composition); a Scheduler reads from an Owner but owns nothing. See
diagrams/uml.mmd.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

PRIORITY_SCORES = {"high": 3, "medium": 2, "low": 1}

TIMES_OF_DAY = ("morning", "afternoon", "evening", "any")

FREQUENCIES = ("daily", "weekly", "custom")

MINUTES_IN_DAY = 24 * 60

# How many days apart each frequency repeats. "custom" takes its gap from the
# task's own interval_days instead, so "every third day" needs no new keyword.
FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "custom": None}

# The stretch of the day each preferred window covers, in minutes since
# midnight. The scheduler places a task inside its window when it can.
WINDOWS = {
    "morning": (5 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, 22 * 60),
    "any": (0, MINUTES_IN_DAY),
}


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

    Recurrence is a gap in days rather than a calendar rule: `frequency` picks
    the usual gaps ("daily", "weekly") and `interval_days` sets any other one.
    `last_completed` records the day the task was last ticked off, which is
    what makes a weekly task stay quiet for six days and a daily one come back
    tomorrow.
    """

    description: str
    duration_minutes: int
    priority: str = "medium"
    category: str = "other"
    fixed_time: str = None
    preferred_time: str = "any"
    frequency: str = "daily"
    interval_days: int = None
    completed: bool = False
    last_completed: date = None
    # The day this occurrence is for. None means "any day". A task spawned by
    # next_occurrence() carries one, which is what stops tomorrow's copy from
    # being planned today.
    due_date: date = None
    # Set once this task has handed over to a successor, so it stays a closed
    # historical record instead of being rolled over into another day.
    retired: bool = field(default=False, repr=False)
    # Parsed once in __post_init__ rather than on every call: the planner asks
    # for the start time several times per task, per build.
    _start: int = field(default=None, init=False, repr=False, compare=False)

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
        if self.frequency not in FREQUENCY_DAYS:
            raise ValueError(
                f"frequency must be one of {list(FREQUENCIES)}, got {self.frequency!r}"
            )
        self.interval_days = self._resolve_interval()
        self.set_fixed_time(self.fixed_time)  # validates and caches the parse
        self.description = self.description.strip()

    def _resolve_interval(self):
        """Settle on one repeat gap in days, from `frequency` and `interval_days`."""
        preset = FREQUENCY_DAYS[self.frequency]
        if self.interval_days is None:
            if preset is None:
                raise ValueError("a custom frequency needs interval_days")
            return preset
        if isinstance(self.interval_days, bool) or not isinstance(
            self.interval_days, int
        ):
            raise ValueError("interval_days must be a positive whole number")
        if self.interval_days <= 0:
            raise ValueError("interval_days must be a positive whole number")
        if preset is not None and self.interval_days != preset:
            raise ValueError(
                f"{self.frequency!r} means every {preset} day(s); use "
                f"frequency='custom' for every {self.interval_days} day(s)"
            )
        return self.interval_days

    # -- anchoring ---------------------------------------------------------

    def set_fixed_time(self, value):
        """Pin the task to "HH:MM", or pass None to unpin it. Caches the parse."""
        self._start = None if value is None else _to_minutes(value)
        self.fixed_time = value
        return self.fixed_time

    def is_anchored(self):
        """True when the owner pinned this task to a specific clock time."""
        return self._start is not None

    def start_minutes(self):
        """The anchored start time in minutes since midnight, or None."""
        return self._start

    def end_minutes(self):
        """The minute an anchored task finishes, or None when it is flexible."""
        return None if self._start is None else self._start + self.duration_minutes

    def spans(self):
        """The stretches of the clock this task occupies, as (start, end) pairs.

        Usually one pair. A task that runs past midnight returns two, because
        23:50 + 30 min covers 23:50-24:00 *and* 00:00-00:20 — and the second
        half is what collides with an early-morning task.
        """
        if self._start is None:
            return []
        end = self._start + self.duration_minutes
        if end <= MINUTES_IN_DAY:
            return [(self._start, end)]
        return [(self._start, MINUTES_IN_DAY), (0, end - MINUTES_IN_DAY)]

    def overlaps(self, other):
        """Do two anchored tasks collide? Touching end to end does not count.

        Each task owns the half-open interval [start, start + duration), so
        the test is `self.start < other.end and other.start < self.end`. The
        strict `<` is what makes 08:00+30 and 08:30 adjacent rather than
        clashing; `<=` would reject a perfectly valid back-to-back pair.
        Two flexible tasks never collide, because neither has a time yet.

        Comparing every span against every span is what catches a task that
        wraps past midnight; without it, 23:50+30 would sort as ending at
        minute 1460 and never meet a 00:05 task sitting at minute 5.
        """
        return any(
            mine_start < theirs_end and theirs_start < mine_end
            for mine_start, mine_end in self.spans()
            for theirs_start, theirs_end in other.spans()
        )

    def window(self):
        """The (start, end) minutes of this task's preferred window."""
        return WINDOWS[self.preferred_time]

    # -- ordering ----------------------------------------------------------

    def priority_score(self):
        """Numeric rank for this task's priority. Higher is more important."""
        return PRIORITY_SCORES[self.priority]

    def sort_key(self):
        """Ordering the scheduler uses for flexible (non-anchored) tasks.

        Highest priority first, then the shortest task, then description so
        that the resulting plan is deterministic and therefore testable.
        """
        return (-self.priority_score(), self.duration_minutes, self.description)

    def time_sort_key(self):
        """Ordering for showing tasks on a clock rather than by importance.

        Pinned tasks come first in clock order; flexible ones follow in the
        order the planner would pick them up, since their time is not settled
        until a plan is built.
        """
        return (
            self._start if self._start is not None else MINUTES_IN_DAY,
            *self.sort_key(),
        )

    # -- completion and recurrence -----------------------------------------

    def mark_complete(self, on=None):
        """Tick this task off for `on` (today by default) and remember the day."""
        self.last_completed = on or date.today()
        self.completed = True
        return self

    def mark_incomplete(self):
        """Put this task back on the to-do list so it gets planned again."""
        self.completed = False
        self.last_completed = None
        return self

    def is_done_for(self, day):
        """Is this task's tick still standing on `day`?

        A tick belongs to the day it was made: a daily feeding ticked off on
        Monday is back on the list by Tuesday. Answering this as a question
        rather than by clearing the flag means building a plan for another day
        can stay read-only. A retired task keeps its tick whatever the day,
        because a successor already carries the work forward.
        """
        if not self.completed:
            return False
        if self.retired or self.last_completed is None:
            return True
        return self.last_completed >= day

    def refresh_for(self, day):
        """Start a new day: clear a tick that belongs to an earlier one.

        Without this, a daily feeding ticked off on Monday would stay ticked
        off forever. `last_completed` survives, so recurrence still knows when
        the task was last actually done. A retired task keeps its tick, because
        a successor already carries it forward.

        The planner uses the read-only `is_done_for` instead; this is for the
        UI, which really does want to roll the checkbox over at the day change.
        """
        if self.completed and not self.is_done_for(day):
            self.completed = False
        return self

    def is_due_on(self, day):
        """Has enough time passed since the last completion for this to recur?"""
        if self.retired:
            return False  # a successor took over; this one is history
        if self.due_date is not None and day < self.due_date:
            return False  # a future occurrence, not today's problem
        if self.last_completed is None:
            return True
        return (day - self.last_completed).days >= self.interval_days

    def next_occurrence(self, on=None):
        """A fresh Task for the next time this one comes round.

        Returns a brand new instance rather than resetting this one, so the
        completed task stays on the record as proof the work was done and the
        successor carries a `due_date` of the next occurrence.
        """
        done_on = on or self.last_completed or date.today()
        return Task(
            description=self.description,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            category=self.category,
            fixed_time=self.fixed_time,
            preferred_time=self.preferred_time,
            frequency=self.frequency,
            interval_days=self.interval_days,
            due_date=done_on + timedelta(days=self.interval_days),
        )

    def next_due_on(self):
        """The first day this task comes round again, or None if never done."""
        if self.last_completed is None:
            return None
        return self.last_completed + timedelta(days=self.interval_days)

    def repeat_text(self):
        """How often this task repeats, in words, for the UI and explanations."""
        if self.interval_days == 1:
            return "daily"
        if self.interval_days == 7:
            return "weekly"
        return f"every {self.interval_days} days"

    # -- filtering ---------------------------------------------------------

    def matches(self, status=None, category=None, priority=None, anchored=None):
        """Does this task pass every filter given? An unset filter always passes.

        One predicate, used by Pet.filter_tasks and Owner.filter_tasks, so a
        new filter is added here once rather than in five list comprehensions.

        An unknown `status` raises rather than quietly matching everything: a
        mistyped filter should not look like a filter that found no matches.
        """
        if status not in (None, "pending", "done"):
            raise ValueError(
                f"status must be 'pending', 'done' or None, got {status!r}"
            )
        if status == "pending" and self.completed:
            return False
        if status == "done" and not self.completed:
            return False
        if category is not None and self.category != category:
            return False
        if priority is not None and self.priority != priority:
            return False
        if anchored is not None and self.is_anchored() is not anchored:
            return False
        return True


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

    def complete_task(self, task, on=None):
        """Tick a task off and queue the next occurrence as a new Task.

        This is the recurring-task entry point: marking "Feeding" done on
        Monday retires that instance and adds a fresh one due Tuesday, so the
        list always holds exactly one pending copy of a repeating task.
        Returns the new Task.
        """
        if isinstance(task, str):
            # Skip retired copies: once "Feeding" has been ticked off, the live
            # task under that name is its successor, not the historical record.
            task = next(
                (t for t in self.tasks if t.description == task and not t.retired),
                None,
            )
            if task is None:
                raise ValueError("no pending task with that description")
        if task not in self.tasks:
            raise ValueError(f"{task.description!r} does not belong to {self.name}")
        if task.retired:
            raise ValueError(
                f"{task.description!r} was already completed on "
                f"{task.last_completed}; its successor is the live one"
            )

        task.mark_complete(on)
        successor = task.next_occurrence(on)
        task.retired = True
        return self.add_task(successor)

    def remove_task(self, description):
        """Remove the first task with this description. True if one was removed."""
        for i, task in enumerate(self.tasks):
            if task.description == description:
                del self.tasks[i]
                return True
        return False

    def remove_task_at(self, index):
        """Remove the task at this position and return it, or None if out of range.

        The UI deletes the row you clicked, which is a position; removing by
        description deletes the wrong one whenever two tasks share a name.
        """
        if not 0 <= index < len(self.tasks):
            return None
        return self.tasks.pop(index)

    def filter_tasks(self, **filters):
        """This pet's tasks matching every filter. See Task.matches()."""
        return [t for t in self.tasks if t.matches(**filters)]

    def tasks_by_time(self):
        """This pet's tasks in clock order: pinned ones first, flexible after."""
        return sorted(self.tasks, key=lambda t: t.time_sort_key())

    def tasks_by_category(self, category):
        """This pet's tasks in one category, such as "meds" or "walk"."""
        return self.filter_tasks(category=category)

    def pending_tasks(self):
        """Tasks still to be done today."""
        return self.filter_tasks(status="pending")

    def completed_tasks(self):
        """Tasks already ticked off today."""
        return self.filter_tasks(status="done")

    def total_task_minutes(self):
        """Minutes of work across every task, done or not."""
        return sum(t.duration_minutes for t in self.tasks)

    def pending_minutes(self):
        """Minutes of work still left to do for this pet."""
        return sum(t.duration_minutes for t in self.pending_tasks())

    def anchor_conflicts(self):
        """Every pair of this pet's pinned tasks whose times collide."""
        anchored = sorted(
            (t for t in self.tasks if t.is_anchored()),
            key=lambda t: t.start_minutes(),
        )
        return [
            (a, b)
            for i, a in enumerate(anchored)
            for b in anchored[i + 1 :]
            if a.overlaps(b)
        ]


# --- Core action 2: consider constraints, across every pet -------------------


@dataclass
class Owner:
    """The person doing the care.

    Manages multiple pets and holds every constraint the Scheduler reads. The
    time budget is a single shared pool: all pets' tasks compete for the same
    `available_minutes`, so the scheduler trades off across pets. `day_start`
    and `day_end` bound the wall clock a plan may use, which the budget on its
    own does not: 60 spare minutes should not put a walk at 23:45.
    """

    name: str
    available_minutes: int = 120
    day_start: str = "08:00"
    day_end: str = "22:00"
    preferred_times: list[str] = field(default_factory=list)
    skip_low_priority: bool = False
    pets: list[Pet] = field(default_factory=list)
    # Bumped by every change the UI can make, so a cached plan can tell that it
    # has gone stale without comparing the whole object graph.
    version: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        """Validate the name, budget and times, and type-check any pets."""
        # Each setter owns its own validation, so the constructor reuses them
        # rather than repeating the same checks.
        self._by_name = {}
        self.rename(self.name)
        self.set_available_minutes(self.available_minutes)
        self.set_day_start(self.day_start)
        self.set_day_end(self.day_end)
        self.set_preferred_times(self.preferred_times)
        incoming, self.pets = list(self.pets), []
        for pet in incoming:
            self.add_pet(pet)
        self.version = 0  # a freshly built owner has not been edited yet

    def touch(self):
        """Record that something a plan depends on changed."""
        self.version += 1
        return self.version

    def _set(self, attribute, value):
        """Assign a constraint, counting it as a change only if it really is one.

        Streamlit replays the whole script on every interaction, so each setter
        is called again with the value it already holds. Bumping the version
        regardless would mark every plan stale a moment after it was built.
        """
        if getattr(self, attribute, object()) != value:
            setattr(self, attribute, value)
            self.touch()
        return value

    def set_preferred_times(self, windows):
        """Set the windows this owner would rather do flexible work in."""
        self._set("preferred_times", list(windows))
        return self.preferred_times

    def set_skip_low_priority(self, skip):
        """Turn the "drop low-priority tasks today" preference on or off."""
        self._set("skip_low_priority", bool(skip))
        return self.skip_low_priority

    # -- validated setters, so the UI can edit a live Owner --------------

    def rename(self, name):
        """Change the owner's name, rejecting an empty one."""
        if not name or not str(name).strip():
            raise ValueError("name cannot be empty")
        self._set("name", str(name).strip())
        return self.name

    def set_available_minutes(self, minutes):
        """Set today's shared time budget, rejecting negatives and non-integers."""
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise ValueError("available_minutes must be zero or a positive whole number")
        if minutes < 0:
            raise ValueError("available_minutes must be zero or a positive whole number")
        self._set("available_minutes", minutes)
        return self.available_minutes

    def set_day_start(self, value):
        """Set the time the day begins, rejecting anything not "HH:MM"."""
        _to_minutes(value)  # validates the format, raises if malformed
        self._set("day_start", value)
        return self.day_start

    def set_day_end(self, value):
        """Set the time the day is over, rejecting anything not "HH:MM"."""
        _to_minutes(value)  # validates the format, raises if malformed
        self._set("day_end", value)
        return self.day_end

    def day_bounds(self):
        """The (start, end) minutes a plan may use.

        An end *before* the start reads as an overnight day, so it runs on to
        midnight rather than leaving the scheduler no room at all. An end equal
        to the start is the one case that really does mean no room: an owner
        who sets both to 08:00 is saying they have no time today, and silently
        handing them sixteen hours would schedule work they cannot do.
        """
        start = _to_minutes(self.day_start)
        end = _to_minutes(self.day_end)
        if end == start:
            return start, start  # an empty day, not a day of unlimited length
        return start, (end if end > start else MINUTES_IN_DAY)

    # -- managing pets ----------------------------------------------------

    def add_pet(self, pet):
        """Put one more pet in this owner's care, and return it."""
        if not isinstance(pet, Pet):
            raise TypeError("add_pet expects a Pet")
        if self.get_pet(pet.name) is not None:
            raise ValueError(f"this owner already has a pet named {pet.name!r}")
        self.pets.append(pet)
        self._index()[pet.name] = pet
        self.touch()
        return pet

    def remove_pet(self, name):
        """Remove the pet with this name. True if one was removed."""
        for i, pet in enumerate(self.pets):
            if pet.name == name:
                del self.pets[i]
                self._by_name.pop(name, None)
                self.touch()
                return True
        return False

    def rename_pet(self, old_name, new_name):
        """Rename a pet, keeping the lookup index in step. Returns the pet."""
        pet = self.get_pet(old_name)
        if pet is None:
            raise ValueError(f"no pet named {old_name!r}")
        if not new_name or not str(new_name).strip():
            raise ValueError("name cannot be empty")
        new_name = str(new_name).strip()
        if new_name != old_name and self.get_pet(new_name) is not None:
            raise ValueError(f"this owner already has a pet named {new_name!r}")
        pet.name = new_name
        self._by_name = None  # renaming invalidates every key, so rebuild lazily
        self.touch()
        return pet

    def get_pet(self, name):
        """The pet with this name, or None. O(1) rather than a scan per lookup."""
        pet = self._index().get(name)
        if pet is None and self.pets:
            # A miss may just mean the index is stale — a pet renamed in place
            # keeps the count the same, so the length check below cannot see it.
            # Rebuilding only on a miss keeps the common hit path O(1).
            self._by_name = None
            pet = self._index().get(name)
        return pet

    def _index(self):
        """The name -> Pet index, rebuilt if `pets` was edited behind its back."""
        by_name = getattr(self, "_by_name", None)
        if by_name is None or len(by_name) != len(self.pets):
            by_name = self._by_name = {pet.name: pet for pet in self.pets}
        return by_name

    # -- access to every pet's tasks ---------------------------------------

    def all_tasks(self):
        """Every task across every pet, as (pet, task) pairs.

        Pairs rather than bare tasks because a plan spanning several pets has
        to be able to say which pet each task belongs to.
        """
        return [(pet, task) for pet in self.pets for task in pet.tasks]

    def filter_tasks(self, pet=None, by_time=False, **filters):
        """Every (pet, task) pair matching the filters given.

        `pet` is a name; the rest are Task.matches() filters (status, category,
        priority, anchored). `by_time` orders the result on the clock instead
        of by pet. Every other task query on Owner goes through here, so the UI
        needs this one method rather than a bespoke one per screen.
        """
        pets = self.pets if pet is None else [p for p in (self.get_pet(pet),) if p]
        pairs = [(p, t) for p in pets for t in p.tasks if t.matches(**filters)]
        if by_time:
            pairs.sort(key=lambda pair: pair[1].time_sort_key())
        return pairs

    def pending_tasks(self):
        """Every not-yet-completed task across every pet, as (pet, task) pairs."""
        return self.filter_tasks(status="pending")

    def completed_tasks(self):
        """Every already-done task across every pet, as (pet, task) pairs."""
        return self.filter_tasks(status="done")

    def total_task_minutes(self):
        """Minutes of work across every pet, done or not."""
        return sum(task.duration_minutes for _, task in self.all_tasks())

    def pending_minutes(self):
        """Minutes of work still left to do across every pet."""
        return sum(task.duration_minutes for _, task in self.pending_tasks())

    def categories(self):
        """Every category actually in use, sorted, so the UI can offer a filter."""
        return sorted({task.category for _, task in self.all_tasks()})

    # -- constraints the scheduler asks about ------------------------------

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

    def _live_anchored(self, on=None):
        """Pinned tasks that could really be scheduled, in clock order.

        Retired and completed tasks are excluded: a finished task is not
        competing for time, and without this a recurring task would be
        reported as clashing with its own replacement.
        """
        live = [
            (pet, task)
            for pet, task in self.all_tasks()
            if task.is_anchored()
            and not task.retired
            and not (task.is_done_for(on) if on is not None else task.completed)
            and (on is None or task.is_due_on(on))
        ]
        return sorted(live, key=lambda pair: pair[1].start_minutes())

    def conflicts_with(self, task, ignoring=None, on=None):
        """Pinned tasks, across every pet, whose time collides with this one.

        Called as a task is added, so a clash is reported at the keyboard
        rather than discovered later when the plan comes back a task short.
        """
        if not task.is_anchored():
            return []
        return [
            (pet, other)
            for pet, other in self._live_anchored(on)
            if other is not task and other is not ignoring and task.overlaps(other)
        ]

    def all_conflicts(self, on=None):
        """Every colliding pair of pinned tasks, as (pet, task, pet, task).

        Pass `on` to judge the clash for one day, so tasks that are not due
        then are left out.
        """
        anchored = self._live_anchored(on)
        return [
            (pet_a, task_a, pet_b, task_b)
            for i, (pet_a, task_a) in enumerate(anchored)
            for pet_b, task_b in anchored[i + 1 :]
            if task_a.overlaps(task_b)
        ]


# --- Core action 3: produce a daily plan and explain it ----------------------


@dataclass
class Scheduler:
    """The brain. Retrieves, organizes and plans tasks across all of an owner's pets.

    Strategy, in order:

    1. Roll yesterday's ticks off, then drop what is already done, not yet due
       again, or low-priority when the owner asked to skip those.
    2. Settle collisions between pinned tasks: the higher priority keeps the
       slot, and on a tie the earlier one does.
    3. Place the surviving pinned tasks at their exact times, claiming budget
       in priority order so a long low-priority pin cannot starve the meds.
    4. Fill the gaps around them with the remaining flexible tasks, highest
       priority first and shortest first on ties, preferring each task's own
       window while it still fits there.
    5. Stop adding work once the shared budget or the owner's day runs out.
    """

    owner: Owner
    # Results of build_plan(), not inputs — init=False keeps them out of the
    # generated __init__ so they cannot be passed in from outside.
    scheduled: list[dict] = field(default_factory=list, init=False)
    skipped: list[dict] = field(default_factory=list, init=False)
    planned: bool = field(default=False, init=False, repr=False)
    plan_date: date = field(default=None, init=False)
    built_at_version: int = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Reject anything that is not a real Owner before planning starts."""
        if not isinstance(self.owner, Owner):
            raise TypeError("Scheduler expects an Owner")
        self._by_pet = {}

    # -- the plan ----------------------------------------------------------

    def build_plan(self, on_date=None):
        """Choose and order the tasks due on `on_date` (today by default).

        Returns the list of scheduled slots, each a dict with `start_time`,
        `pet`, `description`, `duration_minutes`, `priority`, `category`,
        `anchored`, `repeats` and `reason`.
        """
        self.scheduled = []
        self.skipped = []
        self.planned = True
        self.plan_date = on_date or date.today()
        self.built_at_version = self.owner.version

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
                "repeats": p["task"].repeat_text(),
                "reason": self._reason_for(p["task"]),
            }
            for p in placements
        ]

        # Index the finished plan by pet once, rather than rescanning it for
        # every pet in the per-pet views.
        self._by_pet = {}
        for slot in self.scheduled:
            self._by_pet.setdefault(slot["pet"], []).append(slot)

        return self.scheduled

    def is_stale(self):
        """True when the owner changed after this plan was built."""
        return self.planned and self.built_at_version != self.owner.version

    # -- sorting and filtering ---------------------------------------------

    def sort_by_time(self, tasks=None):
        """Every task in clock order: pinned ones by time, then the flexible.

        Takes (pet, task) pairs and defaults to all of the owner's tasks, so
        `scheduler.sort_by_time()` answers "what does the day look like?"
        without having to build a plan first.
        """
        pairs = list(tasks) if tasks is not None else self.owner.all_tasks()
        return sorted(pairs, key=lambda pair: pair[1].time_sort_key())

    def filter_tasks(self, pet=None, by_time=False, **filters):
        """Tasks narrowed by pet name and/or completion status, category, priority.

        Thin pass-through to Owner.filter_tasks so callers holding only a
        Scheduler do not have to reach through to the owner.
        """
        return self.owner.filter_tasks(pet=pet, by_time=by_time, **filters)

    # -- conflict detection -------------------------------------------------

    def find_conflicts(self):
        """Pairs of pinned tasks that collide, as (pet, task, pet, task)."""
        return self.owner.all_conflicts(on=self.plan_date)

    def has_conflicts(self):
        """True when any two pinned tasks want overlapping time."""
        return bool(self.find_conflicts())

    def conflict_warnings(self):
        """Plain-language warnings about clashing pinned tasks.

        Deliberately returns a list of strings rather than raising: a double
        booking is something the owner should see and fix, not a crash. An
        empty list means the day is clean.
        """
        warnings = []
        for pet_a, task_a, pet_b, task_b in self.find_conflicts():
            same = pet_a is pet_b
            who = (
                f"{pet_a.name} is double-booked"
                if same
                else f"{pet_a.name} and {pet_b.name} are both booked"
            )
            warnings.append(
                f"WARNING: {who} at {task_a.fixed_time} — "
                f"{task_a.description} ({task_a.duration_minutes} min, runs to "
                f"{_to_clock(task_a.end_minutes())}) overlaps "
                f"{task_b.description} at {task_b.fixed_time}. "
                f"Only the stronger claim will be scheduled."
            )
        return warnings

    def _gather(self):
        """Collect the tasks due on plan_date, split into anchored and flexible.

        Four filters, in order, each recording a skip reason as it drops a
        task so the explanation can account for everything the owner entered:

        1. Roll yesterday's tick off, so a daily task returns today.
        2. Drop what is already done for today.
        3. Drop what is not due yet, because it repeats on a longer cycle or
           is a successor queued for a later day.
        4. Drop low-priority work when the owner asked to skip it.

        What survives is split by whether it has a fixed time. Anchored tasks
        go on to claim their exact slots; flexible ones are sorted by
        `sort_key()` here so the gap-filling pass can take them in order.
        """
        anchored, flexible = [], []
        day = self.plan_date

        for pet, task in self.owner.all_tasks():
            # Asked, not assigned: planning a day must not edit the tasks, or
            # previewing tomorrow would clear today's completed checkboxes.
            if task.is_done_for(day):
                continue  # already done; nothing to plan
            if not task.is_due_on(day):
                self._skip(pet, task, self._not_due_reason(task, day))
                continue
            if self.owner.skip_low_priority and task.priority == "low":
                self._skip(
                    pet, task, f"{self.owner.name} chose to skip low-priority tasks today"
                )
                continue
            (anchored if task.is_anchored() else flexible).append((pet, task))

        flexible.sort(key=lambda pair: pair[1].sort_key())
        return anchored, flexible

    def _place_anchored(self, anchored):
        """Pin each anchored task to its fixed time, strongest claim first.

        Walking the anchors by priority rather than by clock settles both
        questions the same way: which task keeps a contested slot, and which
        one gets the last of the budget. On equal priority the earlier task
        wins, so a plain overlap still resolves in favour of the first.
        """
        placements = []
        minutes_used = 0

        by_claim = sorted(
            anchored,
            key=lambda pair: (
                -pair[1].priority_score(),
                pair[1].start_minutes(),
                pair[1].sort_key(),
            ),
        )

        for pet, task in by_claim:
            clash = next((p for p in placements if task.overlaps(p["task"])), None)
            if clash is not None:
                other = clash["task"]
                self._skip(
                    pet,
                    task,
                    f"its fixed time {task.fixed_time} overlaps "
                    f"{other.description} for {clash['pet'].name} "
                    f"({other.fixed_time}-{_to_clock(other.end_minutes())}, "
                    f"{other.priority} priority)",
                )
                continue

            if not self.owner.has_capacity_for(minutes_used, task):
                self._skip(pet, task, self._no_time_reason(task, minutes_used))
                continue

            placements.append({"start": task.start_minutes(), "pet": pet, "task": task})
            minutes_used += task.duration_minutes

        placements.sort(key=lambda p: (p["start"], p["task"].sort_key()))
        return placements, minutes_used

    def _place_flexible(self, flexible, anchored_placements, minutes_used):
        """Fit the unanchored tasks into the gaps left between the anchors.

        Greedy, one pass, tasks already in priority order. Each task faces two
        independent limits and is skipped with a different reason for each:
        the shared time budget, and whether any single gap is wide enough.
        Both can fail on their own — there may be budget left but only
        ten-minute gaps, or a two-hour gap but no budget to use it.

        A skip never stops the loop, so a short task later in the list can
        still take a gap that a long one could not. Placing a task splits the
        gap it took, which is why `_claim` has to rebuild the list rather than
        just advance a cursor.
        """
        gaps = self._build_gaps(anchored_placements)
        day_start, day_end = self.owner.day_bounds()
        placements = []

        for pet, task in flexible:
            if not self.owner.has_capacity_for(minutes_used, task):
                self._skip(pet, task, self._no_time_reason(task, minutes_used))
                continue

            slot = self._best_slot(gaps, task)
            if slot is None:
                self._skip(
                    pet,
                    task,
                    f"no {task.duration_minutes} min gap left between "
                    f"{_to_clock(day_start)} and {_to_clock(day_end)}",
                )
                continue

            index, start = slot
            placements.append({"start": start, "pet": pet, "task": task})
            self._claim(gaps, index, start, task.duration_minutes)
            minutes_used += task.duration_minutes

        return placements

    def _build_gaps(self, placements):
        """The free stretches of the day, given the anchored tasks already placed.

        Bounded by the owner's day: the budget alone would happily put a walk
        at 23:45. Anchors outside those bounds are still honored, they just do
        not open up any new room.
        """
        day_start, day_end = self.owner.day_bounds()
        gaps = []
        cursor = day_start
        # placements already arrive in clock order from _place_anchored.
        for placement in placements:
            start = placement["start"]
            if start > cursor:
                gaps.append((cursor, min(start, day_end)))
            cursor = max(cursor, start + placement["task"].duration_minutes)
        gaps.append((cursor, day_end))
        return [(start, end) for start, end in gaps if end > start]

    @staticmethod
    def _best_slot(gaps, task):
        """The earliest start for this task, preferring its own window.

        Two passes: inside the task's preferred window first, then anywhere.
        An evening walk that only fits at 08:00 still beats no walk at all, but
        it should not take the morning slot while the evening is free.
        """
        for low, high in (task.window(), (0, MINUTES_IN_DAY)):
            for index, (gap_start, gap_end) in enumerate(gaps):
                start = max(gap_start, low)
                if start + task.duration_minutes <= min(gap_end, high):
                    return index, start
        return None

    @staticmethod
    def _claim(gaps, index, start, duration):
        """Take [start, start + duration) out of gap `index`, keeping the rest.

        A task placed in the middle of a gap leaves free time on both sides, so
        the gap splits in two rather than simply moving its left edge.
        """
        gap_start, gap_end = gaps[index]
        remainder = [
            (low, high)
            for low, high in ((gap_start, start), (start + duration, gap_end))
            if high > low
        ]
        gaps[index : index + 1] = remainder

    # -- explanation -------------------------------------------------------

    def explain(self):
        """Human-readable reasoning for the plan that build_plan() produced."""
        day_start, day_end = self.owner.day_bounds()
        lines = [
            f"Strategy: fixed-time tasks first, then the rest by highest priority "
            f"and shortest duration, all sharing {self.owner.name}'s "
            f"{self.owner.available_minutes} min between {_to_clock(day_start)} "
            f"and {_to_clock(day_end)}."
        ]

        if not self.planned:
            lines.append("No plan has been built yet — call build_plan() first.")
            return lines

        lines.append(f"Planning for {self.plan_date:%A %d %B}.")

        # Surfaced before the plan itself: a clash explains why a pinned task
        # the owner expected to see is missing from it.
        lines.extend(self.conflict_warnings())

        pet_names = ", ".join(pet.name for pet in self.owner.pets)
        lines.append(
            f"Pets: {pet_names}." if self.owner.pets else "This owner has no pets yet."
        )

        # One pass over the task list, rather than one per question below.
        pairs = self.owner.all_tasks()
        if not pairs:
            lines.append("No care tasks were entered, so the plan is empty.")
            return lines

        # is_done_for, not `completed`: build_plan no longer rolls stale ticks
        # off, so yesterday's feeding must not be reported as done today.
        done = [(pet, task) for pet, task in pairs if task.is_done_for(self.plan_date)]
        if done:
            lines.append(
                "Already done, so left out of the plan: "
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
        """The scheduled slots belonging to one pet, from the index built with
        the plan rather than by rescanning it once per pet."""
        return self._by_pet.get(pet_name, [])

    def skipped_for(self, pet_name):
        """The skipped entries belonging to one pet."""
        return [item for item in self.skipped if item["pet"] == pet_name]

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

    def _not_due_reason(self, task, day):
        """Word the "not due yet" skip message, however the task got there."""
        if task.retired:
            return (
                f"was done on {task.last_completed:%a %d %b}; the next one is "
                f"already queued"
            )
        if task.due_date is not None and day < task.due_date:
            return (
                f"repeats {task.repeat_text()} and is not due until "
                f"{task.due_date:%a %d %b}"
            )
        return (
            f"repeats {task.repeat_text()} and was last done "
            f"{task.last_completed:%a %d %b}, so it is next due "
            f"{task.next_due_on():%a %d %b}"
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
