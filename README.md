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
| `tests/` | `test_models.py` (data classes) and `test_scheduler.py` (the planning brain). |
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

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
.........................................................                [100%]
57 passed in 0.09s
```

`tests/test_models.py` covers the data classes: priority ranking, sort ordering, anchoring,
completion status, managing pets, and input validation. `tests/test_scheduler.py` covers the
planning behaviors that matter: priority ordering, duration tie-breaks, the shared time budget,
fixed-time anchors and their collisions, gap filling, trading off across pets, completion, and
the explanation output.

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `Task.priority_score()`, `Task.sort_key()` | Highest priority first, then shortest duration, then description. The description tie-break makes the plan deterministic and testable. |
| Fixed-time anchoring | `Task.is_anchored()`, `Scheduler._place_anchored()` | Tasks with a `fixed_time` are pinned there first, before anything flexible is placed. |
| Gap filling | `Scheduler._build_gaps()`, `_first_gap_that_fits()` | Flexible tasks are fitted into the free stretches between anchors — a 10-min task will take a 20-min gap that a 60-min task cannot use. |
| Conflict handling | `Scheduler._place_anchored()` | Two anchors that overlap: the earlier one wins, the later is skipped with a reason. Flexible tasks can never overlap, since they only go in gaps. |
| Filtering | `Owner.has_capacity_for()`, `Owner.skip_low_priority` | A task that doesn't fit is skipped with a reason, and the loop **continues** — a shorter task later in the list can still fit. The owner can also drop all low-priority tasks outright. |
| Across pets | `Owner.all_tasks()`, `Owner.pending_tasks()` | All pets share one time budget, so a high-priority task for one pet can beat a low-priority one for another. |
| Completion status | `Task.completed`, `Task.mark_complete()` | Completed tasks are left out of planning entirely and never consume budget. |
| Recurring tasks | `Task.frequency` | Stored (`daily` / `weekly`) but not yet acted on — the planner builds a single day. This is the clearest next feature. |
| Explanation | `Scheduler.explain()`, `Scheduler._reason_for()` | Returns the strategy, a reason per scheduled task, and a reason per skipped task. |

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
