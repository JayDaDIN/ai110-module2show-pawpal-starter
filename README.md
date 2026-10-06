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

## 🖥️ Sample Output

```bash
python main.py
```

One owner with a 100-minute budget, two pets, three fixed-time tasks and three flexible ones.
Full terminal output:

```
==================================================================
                     PawPal+ - Today's Schedule
==================================================================
  Owner:  Jordan
  Budget: 100 min, starting 07:30
  Pets:   Mochi (cat), Biscuit (dog)
  To do:  120 min of pending work
          (20 min more than the day allows)
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
    already done: Evening walk

  WHY THIS PLAN
------------------------------------------------------------------
  Strategy: fixed-time tasks first, then the rest by highest priority and shortest duration, all sharing Jordan's 100 min from 07:30.
  Pets: Mochi, Biscuit.
  Already done, so left out of the plan: Evening walk (Biscuit).
  Scheduled 5 task(s), using 75 of 100 available minutes:
    07:30 — Feeding for Mochi (10 min): pinned to 07:30
    07:40 — Litter box for Mochi (10 min): medium priority
    08:00 — Heartworm meds for Biscuit (5 min): pinned to 08:00
    08:05 — Morning walk for Biscuit (30 min): high priority, and morning matches your preferred window
    18:00 — Play session for Mochi (20 min): pinned to 18:00, and evening matches your preferred window
  Skipped 1 task(s):
    Grooming for Biscuit: needs 45 min but only 25 min of the 100 min budget are left
==================================================================
```

Note the 07:40 litter box: it is a flexible task the scheduler slotted into the 20-minute gap
between Mochi's 07:30 feeding and Biscuit's 08:00 meds, both of which are pinned.

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

### Everything else

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Fixed-time anchoring | `Task.is_anchored()`, `Scheduler._place_anchored()` | Pinned tasks claim their exact times before anything flexible is placed. |
| Gap filling | `Scheduler._build_gaps()`, `_best_slot()`, `_claim()` | Flexible tasks fit into the free stretches between anchors — a 10-min task takes a 20-min gap a 60-min task cannot use. Placing a task mid-gap splits it in two. |
| Preferred windows | `Task.window()`, `Scheduler._best_slot()` | A task is placed inside its own window when it fits there, and anywhere it fits otherwise. |
| Budget | `Owner.has_capacity_for()`, `Owner.skip_low_priority` | A task that doesn't fit is skipped with a reason and the loop **continues**, so a shorter task later can still fit. |
| Across pets | `Owner.all_tasks()`, `Owner.pending_tasks()` | All pets share one time budget, so a high-priority task for one pet can beat a low-priority one for another. |
| Day bounds | `Owner.set_day_end()`, `Owner.day_bounds()` | Nothing is scheduled past the end of the day. |
| Stale plans | `Scheduler.is_stale()`, `Owner.version` | The UI knows when the owner changed after a plan was built. |
| Explanation | `Scheduler.explain()`, `_reason_for()` | The strategy, any conflict warnings, a reason per scheduled task, and a reason per skipped task. |

## 📸 Demo Walkthrough

For the quickest look, run `python main.py` — it builds the sample above and prints it.

For the interactive version, run `streamlit run app.py`, then:

1. **Set your constraints in the sidebar.** Enter the owner name, drag "Time available today" to
   100 minutes, set the day to start at `07:30`, and pick `morning` and `evening` as preferred
   windows. This budget is shared across every pet.
2. **Check your pets.** Mochi and Biscuit are there by default; use the form to add another, or
   remove one (its tasks go with it).
3. **Add care tasks.** Pick which pet each belongs to, then give a description, duration, priority,
   category, and frequency. Leave **Fixed time** blank to let the scheduler choose when the task
   happens, or enter `08:00` to pin it there.
4. **Add a mix.** Pin Mochi's feeding to `07:30` and Biscuit's meds to `08:00`, then add an
   unpinned 10-min litter box and a 30-min walk.
5. **Click Generate schedule.** The plan spans both pets in one timeline. The litter box lands at
   07:40 — the scheduler found the 20-minute gap between the two pinned tasks and fitted it in.
6. **Read the skip warning.** Anything that didn't fit appears in an amber box with the reason:
   out of budget, or no gap big enough between the pinned tasks.
7. **Tick a task's checkbox** to mark it done, then regenerate. It drops out of the plan and stops
   consuming budget, which may free up room for something that was skipped.
8. **Open "Why this plan?"** for the full reasoning: the strategy, which tasks were already done,
   a justification per scheduled task, and the reason for each skip. "Per pet" breaks the same
   plan down by animal.
9. **Try the "Skip low-priority tasks today" checkbox** and regenerate to watch a skip reason
   change from a time constraint to an owner preference.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
