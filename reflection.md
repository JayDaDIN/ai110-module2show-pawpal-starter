# PawPal+ Project Reflection

## 1. System Design

3 Core Actions:

1) Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
2) Consider constraints (time available, priority, owner preferences)
3) Produce a daily plan and explain why it chose that plan

**a. Initial design**

I chose four classes and gave each one exactly one of the three core actions to own, so that every
requirement has a single obvious home. All four live in `pawpal_system.py`, the logic layer, which
is kept separate from the Streamlit UI in `app.py`.

**`CareTask`** — *core action 1: track pet care tasks.*
One unit of care work. Attributes: `title`, `duration_minutes`, `priority`, `category`,
`preferred_time`, `recurrence`. Methods: `priority_score()` maps `high/medium/low` to `3/2/1`, and
`sort_key()` returns `(-priority_score(), duration_minutes, title)`.

Its real responsibility is **defining how tasks rank against each other**. I deliberately put this
on the task rather than in the scheduler so priority is defined in exactly one place and the
scheduler never hardcodes the strings `"high"`/`"medium"`/`"low"`. Changing the ranking rule means
editing one method.

**`Pet`** — *core action 1: hold the tasks.*
The subject of the plan. Attributes: `name`, `species`, `breed`, `energy_level`, and
`tasks: list[CareTask]`. Methods: `add_task()`, `remove_task()`, `tasks_by_category()`,
`total_task_minutes()`.

This is a composition relationship — the pet owns its tasks, and the tasks have no meaning apart
from the pet. `total_task_minutes()` lets the UI show how much work exists before any scheduling
happens, which is what makes an over-budget day visible to the user.

**`Owner`** — *core action 2: consider constraints.*
Every constraint the scheduler reads, in one place. Attributes: `name`, `available_minutes`,
`day_start`, `preferred_times`, `skip_low_priority`. Methods: `has_capacity_for()`,
`minutes_remaining()`, `prefers()`.

The point of this class is that the scheduler never invents its own limits — it asks the owner.
`has_capacity_for()` is the single gate every task passes through, so there is exactly one place
the time budget can be enforced or violated. Adding a new constraint later means adding a field
and a predicate here, not editing the scheduling loop.

**`Scheduler`** — *core action 3: produce a plan and explain it.*
The only class with algorithmic logic. Holds an `Owner` and a `Pet`; produces `scheduled` and
`skipped`. Methods: `build_plan()`, `explain()`, `total_scheduled_minutes()`, plus the private
helpers `_sort_tasks()`, `_reason_for()`, `_advance_time()`.

Concentrating all the logic here is what keeps the tests focused — the other three classes are
data and simple predicates, so almost every meaningful test points at this one class. `explain()`
being a first-class method rather than print statements is what makes the "explain why" requirement
testable: a test can assert the reasoning mentions every scheduled and skipped task.

**Relationships:** `Pet *-- CareTask` is composition (the pet owns its tasks).
`Scheduler --> Owner` and `Scheduler --> Pet` are associations — the scheduler reads from both but
owns neither, so the same pet and owner could be handed to a different scheduling strategy later.

**Implementation note:** `CareTask`, `Pet`, `Owner`, and `Scheduler` are all Python `@dataclass`es.
This gives generated `__init__`, `__repr__`, and `__eq__`, so the classes read as declarations of
what the data *is* rather than boilerplate assignment code, and test failures print full field
values. Validation lives in each class's `__post_init__`, and mutable fields use
`field(default_factory=list)` so instances don't share a list.

**b. Design changes**

The design held up, but reviewing the skeleton against the UML turned up five gaps. All five were
cases where the code allowed something the design never intended.

**1. `Pet` validated tasks on one path but not the other.** `add_task()` rejected anything that
wasn't a `CareTask`, but the constructor accepted any list — `Pet("Mochi", tasks=["Morning walk"])`
built fine and then failed much later with `AttributeError: 'str' object has no attribute
'sort_key'` inside the scheduler. Two ways into the same list with two different rules. The
constructor now routes through `add_task()`, so there is one type check instead of two.

**2. `Scheduler` let you pass in its own results.** Making it a dataclass generated an `__init__`
that accepted `scheduled=` and `skipped=`, so `Scheduler(owner, pet, scheduled=[...])` was legal.
Those are *outputs* of `build_plan()`, not inputs. Marking them `field(init=False)` keeps them out
of the constructor. This was a change the UML already implied — the diagram lists them as
attributes, not constructor parameters — that the dataclass conversion quietly broke.

**3. `explain()` lied before `build_plan()` ran.** It reported "No tasks could be scheduled today,"
which is a claim about a failed attempt, when in fact nothing had been attempted. Added a `planned`
flag so it says "No plan has been built yet" instead. Small, but the whole point of this class is
to explain itself honestly.

**4. Validation was inconsistent across fields.** `priority` and `preferred_time` were checked
against allow-lists; `recurrence` accepted literally anything, including
`"every third tuesday"`. Added a `RECURRENCES` allow-list to match. (`category` is still open on
purpose — an owner might want a custom one.) Also caught that `bool` subclasses `int`, so
`CareTask("Walk", True)` passed as a 1-minute task; that is now rejected.

**5. Weak type hints.** `tasks: list` and `preferred_times: list` became `list[CareTask]` and
`list[str]`, so the dataclass declarations now say what's actually in the collections.

One thing I found and chose **not** to change: `_advance_time()` wraps silently at midnight, so a
plan starting at 23:00 schedules its next task at 00:00 with nothing marking it as the next day.
Fixing it properly means tracking dates, not just clock times, which is more than a single-day
planner needs. I documented it as a known limitation in the method's docstring instead of hiding it.

Earlier, during the first implementation pass, I also added `title` as the final tie-break in
`sort_key()`. Without it, two tasks with the same priority *and* the same duration could come out
in either order, which made the ordering tests flaky. Making the sort fully deterministic is what
allowed the scheduling tests to assert on exact output.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

Three constraints, in order of how strictly they're enforced:

1. **Time budget** (`Owner.available_minutes`) — a hard limit. The plan can never exceed it; there
   is a test asserting this.
2. **Priority** — drives the sort order. High-priority tasks get first claim on the budget.
3. **Owner preferences** — `skip_low_priority` is a hard filter applied before scheduling.
   `preferred_times` is *soft*: it doesn't change the ordering, it only enriches the explanation.

Time ranked highest because it's the constraint the scenario is actually about — a busy owner with
a fixed window. Priority ranked next because for a pet, missing medication is categorically worse
than missing a grooming session. Preferences ranked last because they're about convenience, not
the animal's welfare.

**b. Tradeoffs**

The scheduler is **greedy, not optimal**. It takes tasks highest-priority-first and packs them in,
which can leave the budget under-filled compared to an optimal knapsack packing. With 60 minutes
and tasks of 50/30/10 minutes it schedules the 10 and the 30 (40 min used) rather than finding a
combination that fills all 60.

That tradeoff is right here for two reasons. First, it guarantees the highest-priority needs — meds,
feeding — are never dropped so the app can squeeze in more low-value tasks; an optimizer maximizing
minutes-used could do exactly that. Second, greedy is *explainable*. Core action 3 requires the app
to say why it chose a plan, and "highest priority first, shortest first on ties" is a sentence an
owner can understand and predict. A knapsack solver's output is correct but not defensible in
plain language.

One smaller tradeoff worth naming: when a task doesn't fit, the loop uses `continue` rather than
`break`, so shorter lower-priority tasks can still be scheduled in the leftover time. This
maximizes the number of tasks completed, at the cost of the plan no longer being in strict
priority order. `test_shorter_task_still_fits_after_a_longer_one_is_skipped` pins this behavior.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

30 tests across two files.

`tests/test_care_task.py` — the data layer: priority score mapping, sort ordering (including the
title tie-break), and that bad input is rejected (zero/negative duration, unknown priority,
unknown preferred time, empty title, malformed `day_start`).

`tests/test_scheduler.py` — the behaviors that define the product:

- High-priority tasks scheduled first; shortest-first on ties
- The plan never exceeds the time budget
- A task that doesn't fit is skipped *with a reason*, not silently dropped or truncated
- A shorter task still fits after a longer one is skipped (the `continue`-not-`break` behavior)
- `skip_low_priority` drops low tasks even when there's spare time
- Start times advance correctly, including across an hour boundary (08:45 + 30 → 09:15)
- Empty task list and zero available minutes don't crash
- `explain()` mentions every scheduled *and* skipped task

That last one matters most: "explain why it chose that plan" is a core requirement, so it needs a
test guarding it, not just a method that happens to exist.

**b. Confidence**

Reasonably confident in the scheduling logic — the budget, ordering, and skip behaviors are all
directly asserted, and the sort is deterministic so the tests aren't flaky.

Edge cases I'd test next:
- A plan that runs past midnight (`_advance_time` wraps, but nothing asserts what *should* happen)
- Duplicate task titles
- `preferred_times` actually influencing order, if that becomes a hard constraint in v2
- Recurring tasks — `CareTask.recurrence` is stored but never acted on, so it's currently untested
  because it's unimplemented

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
