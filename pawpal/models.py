"""Core data classes for PawPal+: CareTask, Pet, and Owner."""

PRIORITY_SCORES = {"high": 3, "medium": 2, "low": 1}

TIMES_OF_DAY = ("morning", "afternoon", "evening", "any")


class CareTask:
    """A single thing that needs to happen for the pet."""

    def __init__(
        self,
        title,
        duration_minutes,
        priority="medium",
        category="other",
        preferred_time="any",
        recurrence="daily",
    ):
        if not title or not str(title).strip():
            raise ValueError("title cannot be empty")
        if not isinstance(duration_minutes, int) or duration_minutes <= 0:
            raise ValueError("duration_minutes must be a positive whole number")
        if priority not in PRIORITY_SCORES:
            raise ValueError(
                f"priority must be one of {sorted(PRIORITY_SCORES)}, got {priority!r}"
            )
        if preferred_time not in TIMES_OF_DAY:
            raise ValueError(
                f"preferred_time must be one of {list(TIMES_OF_DAY)}, got {preferred_time!r}"
            )

        self.title = title.strip()
        self.duration_minutes = duration_minutes
        self.priority = priority
        self.category = category
        self.preferred_time = preferred_time
        self.recurrence = recurrence

    def priority_score(self):
        """Numeric rank for this task's priority. Higher is more important."""
        return PRIORITY_SCORES[self.priority]

    def sort_key(self):
        """Ordering used by the scheduler.

        Highest priority first, then the shortest task, then title so that the
        resulting plan is deterministic and therefore testable.
        """
        return (-self.priority_score(), self.duration_minutes, self.title)

    def __repr__(self):
        return (
            f"CareTask({self.title!r}, {self.duration_minutes} min, "
            f"priority={self.priority!r})"
        )


class Pet:
    """The animal the plan is being built for. Owns its list of care tasks."""

    def __init__(self, name, species="dog", breed="", energy_level="medium", tasks=None):
        if not name or not str(name).strip():
            raise ValueError("name cannot be empty")

        self.name = name.strip()
        self.species = species
        self.breed = breed
        self.energy_level = energy_level
        self.tasks = list(tasks) if tasks else []

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

    def __repr__(self):
        return f"Pet({self.name!r}, {self.species!r}, {len(self.tasks)} tasks)"


class Owner:
    """The person doing the care. Holds every constraint the scheduler reads."""

    def __init__(
        self,
        name,
        available_minutes=120,
        day_start="08:00",
        preferred_times=None,
        skip_low_priority=False,
    ):
        if not name or not str(name).strip():
            raise ValueError("name cannot be empty")
        if not isinstance(available_minutes, int) or available_minutes < 0:
            raise ValueError("available_minutes must be zero or a positive whole number")
        _parse_time(day_start)  # validates the format, raises if malformed

        self.name = name.strip()
        self.available_minutes = available_minutes
        self.day_start = day_start
        self.preferred_times = list(preferred_times) if preferred_times else []
        self.skip_low_priority = skip_low_priority

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

    def __repr__(self):
        return f"Owner({self.name!r}, {self.available_minutes} min available)"


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
