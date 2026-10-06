# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🗂️ Project layout

| File | What it holds |
|---|---|
| `pawpal_system.py` | The logic layer: `Task`, `Pet`, `Owner`, `Scheduler`. No UI code. |
| `main.py` | Command-line demo — two pets, mixed fixed and flexible tasks, prints today's schedule. |
| `app.py` | The Streamlit UI. Imports from `pawpal_system`, holds no scheduling logic. |
| `tests/` | `test_models.py` (data classes), `test_scheduler.py` (the planning brain) and `test_features.py` (time ordering, filtering, recurrence, conflicts). |
| `diagrams/uml.mmd` | Class diagram, kept in sync with the code. |

## ⚙️ Features and the algorithms behind them

### The planning algorithm — `Scheduler.build_plan()`

Planning runs as **four ordered passes** rather than one sort. Each pass narrows what the next one
is allowed to do, which is what makes the result explainable line by line.

| Pass | Method | What it does |
|---|---|---|
| 1. Gather | `_gather()` | Drops completed tasks, tasks not due today, and — if `Owner.skip_low_priority` is on — low-priority ones. Completed work is dropped *silently*; it never appears in `skipped`, because "skipped" means "wanted to, couldn't." |
| 2. Anchor | `_place_anchored()` | Pins every fixed-time task to its exact time, walking them in **priority order, not clock order**. The first anchor to claim a slot keeps it, so high priority wins a contested time and the earlier task wins only on a tie. |
| 3. Gaps | `_build_gaps()` | Builds the list of free intervals the anchors left inside `Owner.day_bounds()`. Without this pass a flexible task placed just before an anchor would run straight into it. |
| 4. Fill | `_place_flexible()`, `_best_slot()`, `_claim()` | Walks the flexible tasks in `Task.sort_key()` order and drops each into the first gap it fits. Claiming a slot mid-gap splits that gap in two, so the remainder stays usable. |

**Ordering rule — `Task.sort_key()` → `(-priority_score(), duration_minutes, description)`.**
Highest priority first, shortest first on a tie, then description. That last term looks cosmetic
but is load-bearing: it makes the ordering **total**, so the same inputs always give the same plan
and the tests can assert exact output instead of set membership.

**Greedy, not optimal — and deliberately so.** With 60 minutes and tasks of 50/30/10 the planner
takes the 30 and the 10 (40 used) rather than solving for the packing that fills all 60. A knapsack
solver would use more of the day but could drop medication to fit two cheap tasks, and its output
cannot be defended in a sentence. "Highest priority first, shortest first on ties" can.

**Skipping uses `continue`, not `break`.** When a task overruns the budget the loop keeps going, so
a short low-priority task can still land in the minutes a long high-priority one couldn't use. The
plan is no longer in strict priority order; more tasks get done.

### Gap filling — `_build_gaps()` / `_best_slot()`

Free time is modelled as an explicit list of intervals rather than a single moving cursor. A task
takes the first gap it fits, so **a 10-minute task can use a 20-minute gap a 45-minute task cannot**
— small jobs fill the cracks instead of being pushed to the end of the day. `Task.window()` is
consulted first: a task is placed inside its preferred window when it fits there, and anywhere it
fits otherwise. Preference is a tiebreak, never a reason to drop work.

### Conflict detection — `Task.overlaps()` / `Scheduler.conflict_warnings()`

Overlap compares **full half-open intervals** `[start, start + duration)`, not start times. That is
what catches the realistic clash: a 07:30 feeding running 10 minutes collides with a 07:35
breakfast even though no two numbers match. Half-open is also what lets 08:00+30 and 08:30 sit
back-to-back without being called a conflict — an off-by-one that `<=` would get wrong.

Detection **returns warnings instead of raising**. A double booking is the owner's problem to fix,
not a crash, so the program keeps running, the plan still builds, and the weaker claim is skipped
with a reason naming both tasks and both times.

### Recurrence — `Pet.complete_task()` / `Task.next_occurrence()`

Completing a repeating task **constructs a new `Task` for the next occurrence** and retires the
finished one as a record that the work happened. The successor is stamped with
`due_date = completion + interval_days`, and `Task.is_due_on()` keeps it out of today's plan and
lets it into tomorrow's. The cost of keeping that history is that the task list grows by one per
completion and never shrinks.

### Sorting and filtering — `sort_by_time()` / `filter_tasks()`

`Task.time_sort_key()` orders pinned tasks by start minute and sends flexible ones to the back,
since a flexible task has no time until a plan exists. Filtering runs through a single predicate,
`Task.matches(status, category, priority, anchored)`, which `Pet`, `Owner` and `Scheduler` all
share — a new filter is written once rather than in five list comprehensions.

### At a glance

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Fixed-time anchoring | `Task.is_anchored()`, `_place_anchored()` | A pin is a promise: anchors are never moved, only kept or dropped. |
| Shared budget | `Owner.has_capacity_for()` | One pool across every pet, so Biscuit's meds genuinely out-rank Mochi's playtime. |
| Owner preferences | `Owner.prefers()`, `skip_low_priority` | `skip_low_priority` is a hard pre-filter; `preferred_times` is soft. |
| Day bounds | `Owner.set_day_end()`, `day_bounds()` | Nothing is scheduled past the end of the day. |
| Stale plans | `Scheduler.is_stale()`, `Owner.version` | The owner counts its own changes, so a plan on screen can admit it is out of date. |
| Explanation | `Scheduler.explain()`, `_reason_for()` | A first-class method, not print statements — which is what makes "explain why" testable. |

## 🧪 Testing PawPal+

Run the full suite from the project root:

```bash
python -m pytest
```

### What the tests cover

| File | Covers |
|---|---|
| `tests/test_models.py` | The data classes: priority ranking, sort ordering, anchoring, completion status, adding/removing pets, and input validation. |
| `tests/test_scheduler.py` | The planning brain: priority ordering, duration tie-breaks, the shared time budget, fixed-time anchors and their collisions, gap filling, trade-offs across pets, completion, and the explanation output. |
| `tests/test_features.py` | The four smarter-scheduling features: time ordering, combined filtering, recurrence/successor tasks, and conflict warnings. |
| `tests/test_edge_cases.py` | The awkward inputs: empty task lists, zero and oversized durations, a zero-minute budget, back-to-back and identical pins, tasks running past the end of the day, and every task already done. |
| `tests/test_pawpal.py` | Starter smoke tests that the package imports and the core objects construct. |

### Successful run

```
============================= test session starts =============================
platform win32 -- Python 3.13.1, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\justi\ai110-module2show-pawpal-starter
plugins: anyio-4.14.2
collected 139 items

tests\test_edge_cases.py .....................                           [ 15%]
tests\test_features.py ................................................. [ 50%]
.                                                                        [ 51%]
tests\test_models.py ..................................                  [ 75%]
tests\test_pawpal.py ..                                                  [ 76%]
tests\test_scheduler.py ................................                 [100%]

============================= 139 passed in 0.17s =============================
```

### Confidence Level

**★★★★☆ (4 / 5)**

All 139 tests pass, and they cover the behaviors the app actually depends on: priority ordering,
the shared budget, anchors and their conflicts, gap filling, recurrence, and the edge cases that
usually break schedulers (zero-minute budgets, oversized tasks, identical pins, an empty day).
I'm holding back the fifth star because the suite tests `pawpal_system.py` directly — the Streamlit
layer in `app.py` is only exercised by hand, and the scheduler has not been tried on a large,
messy, real-world task list over many days of recurrence.

## 📐 Smarter Scheduling

Four features beyond basic ordering. Each is described below with the method that implements it;
run `python main.py` to see all four printed in one pass.

### 1. Sorting — `Scheduler.sort_by_time()`

Tasks can be added in any order. `sort_by_time()` returns them on a clock: pinned tasks first in
chronological order, then flexible ones in the order the planner would pick them up (their time
is not settled until a plan is built).

| Method | Role |
|---|---|
| `Scheduler.sort_by_time(tasks=None)` | Entry point. Defaults to every task across every pet; also accepts a filtered list of `(pet, task)` pairs. |
| `Task.time_sort_key()` | The ordering rule: pinned by start minute, flexible after. |
| `Task.sort_key()` | The *importance* ordering the planner uses: priority, then shortest duration, then description. The description tie-break keeps plans deterministic and testable. |
| `Pet.tasks_by_time()` | The same ordering for one pet. |

`main.py` prints "AS ENTERED" directly above "SORTED BY TIME" so the sort is visibly doing work:

```
AS ENTERED (deliberately out of order)     SORTED BY TIME
  18:00     Mochi     Play session           07:30     Mochi     Feeding
  flexible  Mochi     Litter box             07:35     Biscuit   Breakfast
  07:30     Mochi     Feeding                08:00     Biscuit   Heartworm meds
  flexible  Biscuit   Grooming               18:00     Mochi     Play session
  08:00     Biscuit   Heartworm meds         flexible  Biscuit   Morning walk
  flexible  Biscuit   Morning walk           flexible  Mochi     Litter box
  07:35     Biscuit   Breakfast              flexible  Biscuit   Grooming
```

### 2. Filtering — `Scheduler.filter_tasks()`

Narrow the task list by **pet name**, **completion status**, category, priority, or whether a task
is pinned. Filters combine, and `by_time=True` sorts the result.

| Method | Role |
|---|---|
| `Scheduler.filter_tasks(pet=…, by_time=…, **filters)` | Scheduler-level entry point. |
| `Owner.filter_tasks(pet=…, by_time=…, **filters)` | Across every pet, returning `(pet, task)` pairs. |
| `Pet.filter_tasks(**filters)` | Within one pet. |
| `Task.matches(status, category, priority, anchored)` | The single predicate all three share, so a new filter is added once rather than in five list comprehensions. |
| `Pet.pending_tasks()` / `completed_tasks()` | Shorthand for the common status split. |

```python
scheduler.filter_tasks(pet="Mochi")                              # one pet
scheduler.filter_tasks(status="done")                            # completion status
scheduler.filter_tasks(pet="Mochi", status="pending", by_time=True)   # combined
```

### 3. Conflict detection — `Scheduler.conflict_warnings()`

Two tasks pinned to overlapping times return a **warning string rather than raising**. The program
keeps running and the plan still builds; the weaker claim is skipped with a reason.

| Method | Role |
|---|---|
| `Scheduler.conflict_warnings()` | A list of plain-language warnings. Empty list means a clean day. |
| `Scheduler.has_conflicts()` / `find_conflicts()` | Boolean check, and the raw `(pet, task, pet, task)` pairs. |
| `Task.overlaps(other)` | Compares full half-open intervals `[start, start + duration)`, so partial overlaps are caught, not just identical start times. Touching end-to-end is not a clash. |
| `Owner.all_conflicts(on=None)` | Every colliding pair, ignoring completed, retired and not-yet-due tasks. |
| `Owner.conflicts_with(task)` | Checks one task as it is added, so the UI warns at the keyboard. |
| `Scheduler._place_anchored()` | Resolves the clash: the **higher-priority** pin keeps the slot; on equal priority the earlier one wins. |

```
WARNING: Mochi and Biscuit are both booked at 07:30 — Feeding (10 min, runs to
07:40) overlaps Breakfast at 07:35. Only the stronger claim will be scheduled.
```

Warnings also appear at the top of `Scheduler.explain()`, which is where they explain why a pinned
task the owner expected is missing from the plan.

### 4. Recurring tasks — `Pet.complete_task()`

Completing a `daily` or `weekly` task **creates a brand new `Task` instance** for the next
occurrence. The finished one is retired as a record that the work was done.

| Method | Role |
|---|---|
| `Pet.complete_task(task, on=None)` | Marks the task done, retires it, and appends its successor. Returns the new `Task`. |
| `Task.next_occurrence(on=None)` | Builds the successor, copying every setting and stamping a `due_date` of `completion + interval_days`. |
| `Task.is_due_on(day)` | Keeps the successor out of today's plan and lets it in on its due date. |
| `Task.refresh_for(day)` | Rolls an ordinary tick over at midnight; skips retired tasks so a successor is never duplicated. |
| `Task.repeat_text()` | "daily" / "weekly" / "every N days" for the UI. |

```python
successor = mochi.complete_task("Feeding", on=date(2026, 10, 6))
successor.due_date      # 2026-10-07
successor.completed     # False
```

`frequency` accepts `daily`, `weekly`, or `custom` with an explicit `interval_days`, so "every
third day" needs no new keyword.

## 📸 Demo Walkthrough

```bash
streamlit run app.py     # the interactive app
python main.py           # the same system, printed to the terminal
```

### The UI, screen by screen

**Sidebar — "Your day."** Everything here is a constraint, and every widget calls a validated
setter on the live `Owner` rather than assigning a field. You can set the owner's name, drag the
time budget (0–480 minutes), type the start and end of the day as `HH:MM`, pick preferred windows
(morning / afternoon / evening), and tick "Skip low-priority tasks today." Below the divider a
`st.metric` shows pending work, with `st.success` when it fits the budget and `st.warning` when it
doesn't. Any fixed-time clash prints there too, straight from `Scheduler.conflict_warnings()`.

**Your pets.** A form adds a pet (name, species, breed, energy level); the current ones show in an
`st.table` with their task count and pending minutes; a dropdown removes one, and its tasks go with
it. Duplicate names are rejected by `Owner.add_pet()`, so the UI needs no check of its own.

**Care tasks.** A form adds a task to a chosen pet: description, duration, priority, category,
repeat (daily / weekly / every N days), preferred window, and an optional fixed time. Leave the
fixed time blank and the task is *flexible* — the scheduler picks when it happens. Below the form,
four dropdowns filter by pet, status, and category, and order the result by time or by priority.

**Daily plan.** "Generate schedule" builds the plan; "Clear plan" drops it. The plan renders as an
`st.success` summary line plus an `st.table` of time / pet / task / minutes / priority / repeats /
pinned. Skips appear in an `st.warning` with a reason each. Two expanders follow: "Per pet" breaks
the single timeline back down by animal, and "Why this plan?" prints `Scheduler.explain()` in full.

### An example workflow

1. **Add a pet.** In *Your pets*, enter `Biscuit`, species `dog`, breed `Golden Retriever`, energy
   `high`, and click **Add pet**. The table gains a row reading 0 tasks, 0 pending minutes.
2. **Set the day.** In the sidebar, drag the budget to **100 minutes**, set the day to start at
   `07:30`, and select `morning` and `evening` as preferred windows. The budget is shared across
   every pet, not split per animal.
3. **Schedule a pinned task.** In *Care tasks*, pick `Biscuit`, description `Heartworm meds`,
   5 minutes, priority `high`, category `meds`, fixed time `08:00`. Click **Add task**.
4. **Add a flexible one.** Same form, pick `Mochi`, description `Litter box`, 10 minutes, priority
   `medium`, and leave **Fixed time blank**. The scheduler will decide when it happens.
5. **Create a clash on purpose.** Add `Breakfast` for Biscuit pinned to `07:35`, 15 minutes. Mochi's
   07:30 feeding runs to 07:40, so the two overlap — the app warns the moment you submit.
6. **View today's schedule.** Click **Generate schedule**. Both pets appear in one timeline, the
   litter box lands at **07:40** in the gap between the 07:30 feeding and the 08:00 meds, and
   Breakfast is listed under skips with the reason.
7. **Tick something off.** Check a task's box and regenerate. It leaves the plan and stops
   consuming budget, which can make room for a task that was skipped a moment ago. If it repeats,
   a fresh instance is queued for its next due date.
8. **Read the reasoning.** Open **Why this plan?** for the strategy, the conflict warnings, a
   justification per scheduled task, and a reason per skip.

### Scheduler behaviors this shows

| Behavior | Where you see it | Method |
|---|---|---|
| **Sorting** | The task list reordered by the "by time" / "by priority" dropdown — pinned tasks on the clock, flexible ones after | `Scheduler.sort_by_time()`, `Task.sort_key()` |
| **Filtering** | The pet / status / category dropdowns narrowing the table, combining with each other | `Scheduler.filter_tasks()`, `Task.matches()` |
| **Conflict warnings** | The sidebar and the plan both naming Feeding vs Breakfast — a warning, never a crash | `Scheduler.conflict_warnings()`, `Task.overlaps()` |
| **Anchoring** | Meds sitting at exactly 08:00, pinned column marked | `_place_anchored()` |
| **Gap filling** | The 10-minute litter box taking the 20-minute hole at 07:40 | `_build_gaps()`, `_best_slot()` |
| **Budget + skips** | 45-minute grooming skipped "only 25 min left" while shorter tasks still fit | `Owner.has_capacity_for()` |
| **Recurrence** | A ticked daily task reappearing with tomorrow's due date | `Pet.complete_task()` |
| **Explanation** | The "Why this plan?" expander | `Scheduler.explain()` |

### Sample CLI output

`python main.py` runs the same system headlessly: one owner with a 100-minute budget, two pets, and
seven tasks entered deliberately out of order, with one fixed-time clash planted in.

```
==================================================================
                     PawPal+ - Today's Schedule
==================================================================
  Owner:  Jordan
  Budget: 100 min, starting 07:30
  Pets:   Mochi (cat), Biscuit (dog)
  To do:  130 min of pending work
          (30 min more than the day allows)

  AS ENTERED (deliberately out of order)
------------------------------------------------------------------
  18:00     Mochi     Play session
  flexible  Mochi     Litter box
  07:30     Mochi     Feeding
  flexible  Biscuit   Grooming
  08:00     Biscuit   Heartworm meds
  flexible  Biscuit   Morning walk
  07:35     Biscuit   Breakfast

  SORTED BY TIME  (Scheduler.sort_by_time)
------------------------------------------------------------------
  07:30     Mochi     Feeding
  07:35     Biscuit   Breakfast
  08:00     Biscuit   Heartworm meds
  18:00     Mochi     Play session
  flexible  Biscuit   Morning walk
  flexible  Mochi     Litter box
  flexible  Biscuit   Grooming

  CONFLICT CHECK  (Scheduler.conflict_warnings)
------------------------------------------------------------------
  WARNING: Mochi and Biscuit are both booked at 07:30 — Feeding (10 min, runs to 07:40) overlaps Breakfast at 07:35. Only the stronger claim will be scheduled.
  (1 warning(s) — the program keeps running.)

  TODAY'S SCHEDULE
------------------------------------------------------------------
  TIME   PET       TASK                     MINS  PRIORITY
------------------------------------------------------------------
* 07:30  Mochi     Feeding                    10  high
  07:40  Mochi     Litter box                 10  medium
* 08:00  Biscuit   Heartworm meds              5  high
  08:05  Biscuit   Morning walk               30  high
* 18:00  Mochi     Play session               20  medium
------------------------------------------------------------------
  5 task(s), 75 of 100 minutes used.
  * = pinned to a fixed time

  NOT TODAY
------------------------------------------------------------------
  Breakfast (Biscuit)
    reason: its fixed time 07:35 overlaps Feeding for Mochi (07:30-07:40, high priority)
  Grooming (Biscuit)
    reason: needs 45 min but only 25 min of the 100 min budget are left

  BY PET
------------------------------------------------------------------
  Mochi (Tabby) - 3 task(s), 40 min
    07:30  Feeding
    07:40  Litter box
    18:00  Play session
  Biscuit (Golden Retriever) - 2 task(s), 35 min
    08:00  Heartworm meds
    08:05  Morning walk

  FILTERS  (Scheduler.filter_tasks)
------------------------------------------------------------------
  pet=Mochi     Play session, Litter box, Feeding
  pet=Biscuit   Grooming, Heartworm meds, Morning walk, Breakfast
  status=pending Play session, Litter box, Feeding, Grooming, Heartworm meds, Morning walk, Breakfast
  status=done   (none)

  WHY THIS PLAN
------------------------------------------------------------------
  Strategy: fixed-time tasks first, then the rest by highest priority and shortest duration, all sharing Jordan's 100 min between 07:30 and 22:00.
  Planning for Tuesday 06 October.
  WARNING: Mochi and Biscuit are both booked at 07:30 — Feeding (10 min, runs to 07:40) overlaps Breakfast at 07:35. Only the stronger claim will be scheduled.
  Pets: Mochi, Biscuit.
  Scheduled 5 task(s), using 75 of 100 available minutes:
    07:30 — Feeding for Mochi (10 min): pinned to 07:30
    07:40 — Litter box for Mochi (10 min): medium priority
    08:00 — Heartworm meds for Biscuit (5 min): pinned to 08:00
    08:05 — Morning walk for Biscuit (30 min): high priority, and morning matches your preferred window
    18:00 — Play session for Mochi (20 min): pinned to 18:00, and evening matches your preferred window
  Skipped 2 task(s):
    Breakfast for Biscuit: its fixed time 07:35 overlaps Feeding for Mochi (07:30-07:40, high priority)
    Grooming for Biscuit: needs 45 min but only 25 min of the 100 min budget are left

  RECURRENCE  (Pet.complete_task)
------------------------------------------------------------------
  Ticked off 'Feeding' for Mochi on Tue 06 Oct.
  Mochi's task count: 3 -> 4
  New instance queued: 'Feeding' (daily) due Wed 07 Oct, completed=False
  Plan for Wed 07 Oct contains 1 'Feeding' (the successor, not a duplicate).
==================================================================
```

Three things to notice in that output. **07:40** — the litter box is flexible, and the scheduler
fitted it into the 20-minute hole between two pinned tasks rather than appending it to the end.
**Breakfast** — a pinned task lost its slot to a higher-priority pin and was reported, not crashed
on. **Grooming** — it needed 45 minutes and only 25 remained, so it was skipped while shorter tasks
that came after it still got scheduled.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
