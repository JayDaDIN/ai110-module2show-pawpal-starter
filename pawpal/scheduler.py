"""Greedy daily planner for PawPal+."""

from .models import Owner, Pet, _parse_time


class Scheduler:
    """Builds a daily plan for a pet, within an owner's constraints.

    Strategy: sort tasks by priority (high first), break ties by the shortest
    task, then pack them into the owner's time budget in that order.
    """

    def __init__(self, owner, pet):
        if not isinstance(owner, Owner):
            raise TypeError("Scheduler expects an Owner")
        if not isinstance(pet, Pet):
            raise TypeError("Scheduler expects a Pet")

        self.owner = owner
        self.pet = pet
        self.scheduled = []
        self.skipped = []

    def build_plan(self):
        """Choose and order today's tasks. Returns the list of scheduled slots."""
        self.scheduled = []
        self.skipped = []

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

        if not self.pet.tasks:
            lines.append(f"No care tasks were entered for {self.pet.name}, so the plan is empty.")
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
        """Add minutes to an "HH:MM" string, wrapping at midnight."""
        hours, mins = _parse_time(clock)
        total = (hours * 60 + mins + minutes) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
