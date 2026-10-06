"""PawPal+ logic layer.

All four backend classes live here, separate from the Streamlit UI in app.py:

    CareTask  - one unit of pet care work          (track tasks)
    Pet       - the animal the plan is built for   (track tasks)
    Owner     - every scheduling constraint        (consider constraints)
    Scheduler - builds the plan and explains it    (produce a daily plan)

Relationships: a Pet owns its CareTasks (composition); a Scheduler reads from an
Owner and a Pet but owns neither (association). See diagrams/uml.mmd.
"""

from dataclasses import dataclass, field

PRIORITY_SCORES = {"high": 3, "medium": 2, "low": 1}

TIMES_OF_DAY = ("morning", "afternoon", "evening", "any")

RECURRENCES = ("daily", "weekly")


def _parse_time(value):
    """Turn "08:30" into (8, 30). Raises ValueError on anything else."""
    try:
        hours, minutes = str(value).split(":")
        hours, minutes = int(hours), int(minutes)
    except (ValueError, AttributeError):
        raise ValueError(f"time must look like 'HH:MM', got {value!r}")
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError(f"time out of range: {value!r}")
    return hours, minutes


# --- Core action 1: track pet care tasks -------------------------------------


@dataclass
class CareTask:
    """A single thing that needs to happen for the pet."""

    title: str
    duration_minutes: int
    priority: str = "medium"
    category: str = "other"
    preferred_time: str = "any"
    recurrence: str = "daily"

    def __post_init__(self):
        if not self.title or not str(self.title).strip():
            raise ValueError("title cannot be empty")
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
        if self.recurrence not in RECURRENCES:
            raise ValueError(
                f"recurrence must be one of {list(RECURRENCES)}, got {self.recurrence!r}"
            )
        self.title = self.title.strip()

    def priority_score(self):
        """Numeric rank for this task's priority. Higher is more important."""
        return PRIORITY_SCORES[self.priority]

    def sort_key(self):
        """Ordering used by the scheduler.

        Highest priority first, then the shortest task, then title so that the
        resulting plan is deterministic and therefore testable.
        """
        return (-self.priority_score(), self.duration_minutes, self.title)


@dataclass
class Pet:
    """The animal the plan is being built for. Owns its list of care tasks."""

    name: str
    species: str = "dog"
    breed: str = ""
    energy_level: str = "medium"
    tasks: list["CareTask"] = field(default_factory=list)

    def __post_init__(self):
        if not self.name or not str(self.name).strip():
            raise ValueError("name cannot be empty")
        self.name = self.name.strip()
        # Route the constructor through add_task so tasks passed in are held to
        # the same type check as tasks added later.
        incoming, self.tasks = list(self.tasks), []
        for task in incoming:
            self.add_task(task)

    def add_task(self, task):
        if not isinstance(task, CareTask):
            raise TypeError("add_task expects a CareTask")
        self.tasks.append(task)
        return task

    def remove_task(self, title):
        """Remove the first task with this title. Returns True if one was removed."""
        for i, task in enumerate(self.tasks):
            if task.title == title:
                del self.tasks[i]
                return True
        return False

    def tasks_by_category(self, category):
        return [t for t in self.tasks if t.category == category]

    def total_task_minutes(self):
        return sum(t.duration_minutes for t in self.tasks)


# --- Core action 2: consider constraints -------------------------------------


@dataclass
class Owner:
    """The person doing the care. Holds every constraint the scheduler reads."""

    name: str
    available_minutes: int = 120
    day_start: str = "08:00"
    preferred_times: list[str] = field(default_factory=list)
    skip_low_priority: bool = False

    def __post_init__(self):
        if not self.name or not str(self.name).strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.available_minutes, int) or self.available_minutes < 0:
            raise ValueError("available_minutes must be zero or a positive whole number")
        _parse_time(self.day_start)  # validates the format, raises if malformed
        self.name = self.name.strip()
        self.preferred_times = list(self.preferred_times)

    def has_capacity_for(self, minutes_used, task):
        """Can this task still fit in the day's remaining budget?"""
        return minutes_used + task.duration_minutes <= self.available_minutes

    def minutes_remaining(self, minutes_used):
        return max(0, self.available_minutes - minutes_used)

    def prefers(self, task):
        """Does this task land in one of the owner's preferred windows?"""
        if not self.preferred_times or task.preferred_time == "any":
            return False
        return task.preferred_time in self.preferred_times


# --- Core action 3: produce a daily plan and explain it ----------------------


@dataclass
class Scheduler:
    """Builds a daily plan for a pet, within an owner's constraints.

    Strategy: sort tasks by priority (high first), break ties by the shortest
    task, then pack them into the owner's time budget in that order.
    """

    owner: Owner
    pet: Pet
    # Results of build_plan(), not inputs — init=False keeps them out of the
    # generated __init__ so they cannot be passed in from outside.
    scheduled: list[dict] = field(default_factory=list, init=False)
    skipped: list[dict] = field(default_factory=list, init=False)
    planned: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.owner, Owner):
            raise TypeError("Scheduler expects an Owner")
        if not isinstance(self.pet, Pet):
            raise TypeError("Scheduler expects a Pet")

    def build_plan(self):
        """Choose and order today's tasks. Returns the list of scheduled slots."""
        self.scheduled = []
        self.skipped = []
        self.planned = True

        candidates = []
        for task in self.pet.tasks:
            if self.owner.skip_low_priority and task.priority == "low":
                self.skipped.append(
                    {
                        "title": task.title,
                        "priority": task.priority,
                        "duration_minutes": task.duration_minutes,
                        "reason": (
                            f"{self.owner.name} chose to skip low-priority tasks today"
                        ),
                    }
                )
            else:
                candidates.append(task)

        clock = self.owner.day_start
        minutes_used = 0

        for task in self._sort_tasks(candidates):
            if not self.owner.has_capacity_for(minutes_used, task):
                remaining = self.owner.minutes_remaining(minutes_used)
                self.skipped.append(
                    {
                        "title": task.title,
                        "priority": task.priority,
                        "duration_minutes": task.duration_minutes,
                        "reason": (
                            f"needs {task.duration_minutes} min but only {remaining} min "
                            f"of the {self.owner.available_minutes} min budget are left"
                        ),
                    }
                )
                # Keep going rather than stopping: a shorter task later in the
                # list may still fit in the time that remains.
                continue

            self.scheduled.append(
                {
                    "start_time": clock,
                    "title": task.title,
                    "category": task.category,
                    "duration_minutes": task.duration_minutes,
                    "priority": task.priority,
                    "reason": self._reason_for(task),
                }
            )
            clock = self._advance_time(clock, task.duration_minutes)
            minutes_used += task.duration_minutes

        return self.scheduled

    def explain(self):
        """Human-readable reasoning for the plan that build_plan() produced."""
        lines = [
            f"Strategy: highest priority first, shortest task first on ties, "
            f"packed into {self.owner.name}'s {self.owner.available_minutes} min "
            f"starting at {self.owner.day_start}."
        ]

        if not self.planned:
            lines.append("No plan has been built yet — call build_plan() first.")
            return lines

        if not self.pet.tasks:
            lines.append(
                f"No care tasks were entered for {self.pet.name}, so the plan is empty."
            )
            return lines

        if self.scheduled:
            lines.append(
                f"Scheduled {len(self.scheduled)} task(s) for {self.pet.name}, "
                f"using {self.total_scheduled_minutes()} of "
                f"{self.owner.available_minutes} available minutes:"
            )
            for slot in self.scheduled:
                lines.append(
                    f"  {slot['start_time']} — {slot['title']} "
                    f"({slot['duration_minutes']} min): {slot['reason']}"
                )
        else:
            lines.append("No tasks could be scheduled today.")

        if self.skipped:
            lines.append(f"Skipped {len(self.skipped)} task(s):")
            for item in self.skipped:
                lines.append(f"  {item['title']}: {item['reason']}")

        return lines

    def total_scheduled_minutes(self):
        return sum(slot["duration_minutes"] for slot in self.scheduled)

    def _sort_tasks(self, tasks):
        return sorted(tasks, key=lambda t: t.sort_key())

    def _reason_for(self, task):
        reason = f"{task.priority} priority"
        if self.owner.prefers(task):
            reason += f", and {task.preferred_time} matches your preferred window"
        return reason

    @staticmethod
    def _advance_time(clock, minutes):
        """Add minutes to an "HH:MM" string, wrapping at midnight.

        Known limitation: the wrap is silent. A plan starting at 23:00 with a
        120-minute budget schedules its second task at 00:00 with nothing to
        say that is the next day. Acceptable for now because this is a
        single-day planner and realistic start times are in the morning.
        """
        hours, mins = _parse_time(clock)
        total = (hours * 60 + mins + minutes) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
