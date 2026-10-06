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

**`Task`** — *core action 1: track pet care tasks.*
One care activity. Attributes: `description`, `duration_minutes`, `fixed_time`, `frequency`,
`completed`, plus `priority`, `category` and `preferred_time`. Methods: `priority_score()` maps
`high/medium/low` to `3/2/1`; `sort_key()` returns
`(-priority_score(), duration_minutes, description)`; `is_anchored()` and `start_minutes()` report
whether and when the task is pinned; `mark_complete()` / `mark_incomplete()` toggle its status.

"Time" is deliberately split into two fields. `duration_minutes` is how long the task takes;
`fixed_time` is an optional `"HH:MM"` anchor. A task with no `fixed_time` is *flexible* — the
scheduler decides when it happens. That split is what lets the same class express both
"walk the dog for 30 minutes sometime" and "meds at 08:00 sharp."

Its other real responsibility is **defining how tasks rank against each other**. I put this on the
task rather than in the scheduler so priority is defined in exactly one place and the scheduler
never hardcodes the strings `"high"`/`"medium"`/`"low"`.

**`Pet`** — *core action 1: hold the tasks.*
Pet details plus the tasks belonging to that pet. Attributes: `name`, `species`, `breed`,
`energy_level`, `tasks: list[Task]`. Methods: `add_task()`, `remove_task()`,
`tasks_by_category()`, `pending_tasks()`, `completed_tasks()`, `total_task_minutes()`,
`pending_minutes()`.

This is composition — the pet owns its tasks, and the tasks have no meaning apart from the pet.
Separating `pending_tasks()` from `completed_tasks()` here means the scheduler never has to filter
on `completed` itself.

**`Owner`** — *core action 2: manage pets and constraints.*
Manages multiple pets and holds every constraint. Attributes: `name`, `available_minutes`,
`day_start`, `preferred_times`, `skip_low_priority`, `pets: list[Pet]`. Methods: `add_pet()`,
`remove_pet()`, `get_pet()`, `all_tasks()`, `pending_tasks()`, `completed_tasks()`,
`has_capacity_for()`, `minutes_remaining()`, `prefers()`, `is_overcommitted()`.

Two responsibilities, and both matter. First, **it is the single source of constraints** — the
scheduler never invents its own limits, it asks the owner, and `has_capacity_for()` is the one gate
every task passes through. Second, **it is the access point for every pet's tasks**: `all_tasks()`
returns `(pet, task)` pairs rather than bare tasks, because a plan spanning several animals has to
be able to say which pet each item belongs to.

The time budget is a single shared pool rather than one slice per pet. That is the decision that
makes the scheduler a real planner: Biscuit's medication can out-rank Mochi's playtime, which could
not happen if each pet were scheduled independently.

**`Scheduler`** — *core action 3: produce a plan and explain it.*
The brain, and the only class with algorithmic logic. Holds an `Owner`; produces `scheduled`,
`skipped` and `planned`. Methods: `build_plan()`, `explain()`, `total_scheduled_minutes()`,
`tasks_for()`, plus the private helpers `_gather()`, `_place_anchored()`, `_place_flexible()`,
`_build_gaps()` and `_first_gap_that_fits()`.

It plans in four passes: drop completed and (optionally) low-priority tasks; pin the anchored tasks
to their fixed times; compute the free gaps those anchors leave; then fill the gaps with the
flexible tasks, highest priority and shortest first, until the shared budget runs out.

Concentrating the logic here keeps the tests focused — the other three classes are data and simple
predicates, so almost every meaningful test points at this one class. `explain()` being a
first-class method rather than print statements is what makes the "explain why" requirement
testable: a test can assert the reasoning mentions every scheduled and skipped task.

**Relationships:** `Owner *-- Pet` and `Pet *-- Task` are both composition. `Scheduler --> Owner`
is an association — the scheduler reads from the owner but owns nothing, so the same owner could be
handed to a different scheduling strategy later.

**Implementation note:** `Task`, `Pet`, `Owner`, and `Scheduler` are all Python `@dataclass`es.
This gives generated `__init__`, `__repr__`, and `__eq__`, so the classes read as declarations of
what the data *is* rather than boilerplate assignment code, and test failures print full field
values. Validation lives in each class's `__post_init__`, and mutable fields use
`field(default_factory=list)` so instances don't share a list.

**b. Design changes**

### The big one: one pet became many

The first version scheduled for a single pet — `Scheduler(owner, pet)` — and `Owner` held nothing
but constraints. Restructuring so an owner manages *multiple* pets changed all four classes:

- **`Owner` gained a second responsibility.** It now owns `pets: list[Pet]` and exposes
  `all_tasks()` / `pending_tasks()` as `(pet, task)` pairs. I considered giving each pet its own
  time slice, but a shared budget is what makes the scheduler interesting: with one pool, a
  high-priority task for one animal genuinely competes with a low-priority task for another.
  With separate slices the scheduler would just be running the same algorithm N times.
- **`Scheduler` dropped its `pet` parameter.** It takes only an `Owner` now and reaches the pets
  through it. Every slot in the plan carries a `pet` name, and `tasks_for(pet_name)` filters the
  one timeline back down per animal.
- **`CareTask` became `Task`**, with `title` → `description` and `recurrence` → `frequency`.

### Splitting "time" into two fields

The bigger conceptual change was `Task.fixed_time`. Originally every task was flexible and the
scheduler assigned all the clock times. But real pet care has appointments — medication at 08:00
is not negotiable. Rather than add a separate `Appointment` class (which would have made five
classes), I gave `Task` an optional `fixed_time` and let `is_anchored()` distinguish the two kinds.

That forced the scheduling algorithm to change from a single greedy pass into four:

1. Drop completed tasks, and low-priority ones if the owner asked.
2. Place anchored tasks at their fixed times.
3. Compute the free gaps those anchors leave.
4. Fill the gaps with flexible tasks, highest priority and shortest first.

Step 3 is the part I did not anticipate. Without it, a flexible task placed right before an anchor
would overlap it. Building an explicit list of gaps and asking `_first_gap_that_fits()` for the
first one big enough also produced a nicer behavior for free: a short task will happily take a
20-minute gap that a long task cannot use, so small jobs fill the cracks rather than being pushed
to the end of the day. In the demo, Mochi's litter box lands at 07:40 precisely because it fits
between the 07:30 feeding and the 08:00 meds.

### Completion status

Adding `Task.completed` raised a question the old design never had to answer: is a finished task
*skipped*? I decided no. Completed tasks are left out of the plan silently and never appear in
`skipped`, because `skipped` means "we wanted to do this and could not" — a reason the owner might
act on. Finished work is reported separately by `explain()` under "Already done." They also do not
consume budget, so ticking something off can free up room for a task that was previously skipped.

### Earlier fixes, from reviewing the skeleton

Reviewing the skeleton against the UML turned up five gaps, all cases where the code allowed
something the design never intended.

**1. `Pet` validated tasks on one path but not the other.** `add_task()` rejected anything that
wasn't a `Task`, but the constructor accepted any list — `Pet("Mochi", tasks=["Morning walk"])`
built fine and then failed much later with `AttributeError: 'str' object has no attribute
'sort_key'` inside the scheduler. Two ways into the same list with two different rules. The
constructor now routes through `add_task()`, so there is one type check instead of two.

**2. `Scheduler` let you pass in its own results.** Making it a dataclass generated an `__init__`
that accepted `scheduled=` and `skipped=`, so `Scheduler(owner, scheduled=[...])` was legal.
Those are *outputs* of `build_plan()`, not inputs. Marking them `field(init=False)` keeps them out
of the constructor. This was a change the UML already implied — the diagram lists them as
attributes, not constructor parameters — that the dataclass conversion quietly broke.

**3. `explain()` lied before `build_plan()` ran.** It reported "No tasks could be scheduled today,"
which is a claim about a failed attempt, when in fact nothing had been attempted. Added a `planned`
flag so it says "No plan has been built yet" instead. Small, but the whole point of this class is
to explain itself honestly.

**4. Validation was inconsistent across fields.** `priority` and `preferred_time` were checked
against allow-lists; `frequency` accepted literally anything, including
`"every third tuesday"`. Added a `FREQUENCIES` allow-list to match. (`category` is still open on
purpose — an owner might want a custom one.) Also caught that `bool` subclasses `int`, so
`Task("Walk", True)` passed as a 1-minute task; that is now rejected.

**5. Weak type hints.** `tasks: list` and `preferred_times: list` became `list[Task]` and
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

Four constraints, in order of how strictly they're enforced:

1. **Fixed times** (`Task.fixed_time`) — the hardest constraint. An anchored task happens at its
   stated time or not at all; it is never moved. The only thing that can displace one is another
   anchor that got there first.
2. **Time budget** (`Owner.available_minutes`) — a hard limit, shared across every pet. The plan
   can never exceed it; there is a test asserting this.
3. **Priority** — drives the sort order for everything that isn't anchored. High-priority tasks
   get first claim on whatever budget the anchors leave.
4. **Owner preferences** — `skip_low_priority` is a hard filter applied before scheduling.
   `preferred_times` is *soft*: it doesn't change the ordering, it only enriches the explanation.

Fixed times rank highest because they represent commitments the owner has already made — a vet
appointment or a medication window isn't something a planner gets to second-guess. Time ranked
next because it's the constraint the scenario is actually about: a busy owner with a fixed window.
Priority after that, because for a pet, missing medication is categorically worse than missing a
grooming session. Preferences last, because they're about convenience, not the animal's welfare.

Note that priority deliberately does **not** out-rank anchoring. A low-priority task pinned to
08:00 keeps that slot even if a high-priority flexible task wants it. That looks wrong at first,
but the owner pinned it on purpose, and silently moving a task the owner explicitly scheduled
would make the app untrustworthy.

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

Two smaller tradeoffs worth naming.

When a task doesn't fit, the loop uses `continue` rather than `break`, so shorter lower-priority
tasks can still be scheduled in the leftover time. This maximizes the number of tasks completed, at
the cost of the plan no longer being in strict priority order.
`test_shorter_task_still_fits_after_a_longer_one_is_skipped` pins this behavior.

When two anchored tasks overlap, the **earlier** one wins and the later is skipped — not the
higher-priority one. Priority-wins would arguably be the better outcome for the pet, but
earlier-wins is the rule an owner can predict without running the scheduler in their head, and the
skip message names the exact conflict so they can fix it themselves. If this app grew, that is the
first rule I'd revisit.

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

57 tests across two files.

`tests/test_models.py` — the data layer: priority score mapping, sort ordering (including the
description tie-break), anchoring (`is_anchored()` / `start_minutes()`), completion toggling,
managing pets (add, remove, look up, reject duplicate names), `all_tasks()` spanning every pet,
and that bad input is rejected (zero/negative/boolean duration, unknown priority, preferred time
or frequency, malformed `fixed_time` and `day_start`, empty description).

`tests/test_scheduler.py` — the behaviors that define the product:

- High-priority tasks scheduled first; shortest-first on ties
- The plan never exceeds the shared time budget
- A task that doesn't fit is skipped *with a reason*, not silently dropped or truncated
- A shorter task still fits after a longer one is skipped (the `continue`-not-`break` behavior)
- Anchored tasks land at their exact fixed time, even when lower priority than flexible ones
- Flexible tasks fill the gap *before* an anchor when they fit, and go after it when they don't
- Two overlapping anchors: the earlier one wins, the later is skipped with a reason
- Anchors that touch end-to-end (08:00+30 then 08:30) are *not* treated as overlapping
- Anchored tasks count against the same shared budget as flexible ones
- The plan spans every pet, labels each slot with its pet, and `tasks_for()` filters it back down
- Priority beats pet order: a tight budget gives the second pet's high-priority task the slot
- Completed tasks are left out of the plan and don't consume budget
- `skip_low_priority` drops low tasks even when there's spare time
- Start times advance correctly, including across an hour boundary (08:45 + 30 → 09:15)
- Empty task list, no pets, and zero available minutes don't crash
- `explain()` mentions every scheduled *and* skipped task, and says so before `build_plan()` runs

That last one matters most: "explain why it chose that plan" is a core requirement, so it needs a
test guarding it, not just a method that happens to exist.

The anchor tests were the ones that caught real bugs. The end-to-end case in particular — two
anchors where one ends exactly when the next begins — is an off-by-one trap: using `<=` instead of
`<` in the overlap check would wrongly reject a perfectly valid back-to-back pair.

**b. Confidence**

Reasonably confident in the scheduling logic — the budget, ordering, anchoring and skip behaviors
are all directly asserted, and the sort is deterministic so the tests aren't flaky.

Edge cases I'd test next:
- A plan that runs past midnight (`_to_clock` wraps, but nothing asserts what *should* happen, and
  a 23:00 start silently produces a 00:00 slot with no "next day" marker)
- Duplicate task descriptions on the same pet
- An anchored task whose fixed time is before `day_start` — currently honored, but is that right?
- `preferred_times` actually influencing order, if that becomes a hard constraint in v2
- Recurring tasks — `Task.frequency` is stored but never acted on, so it's currently untested
  because it's unimplemented

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
