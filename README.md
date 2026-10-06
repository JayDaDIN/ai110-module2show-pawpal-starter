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

## 🖥️ Sample Output

With a 60-minute budget starting at 08:00, a preferred "morning" window, and three tasks
(a 30-min high-priority walk, a 10-min high-priority feeding, and a 45-min low-priority grooming):

```
Daily plan for Biscuit (Golden Retriever):
  08:00 - Feeding (10 min) [priority: high]
  08:10 - Morning walk (30 min) [priority: high]

Strategy: highest priority first, shortest task first on ties, packed into Jordan's 60 min starting at 08:00.
Scheduled 2 task(s) for Biscuit, using 40 of 60 available minutes:
  08:00 — Feeding (10 min): high priority, and morning matches your preferred window
  08:10 — Morning walk (30 min): high priority, and morning matches your preferred window
Skipped 1 task(s):
  Grooming: needs 45 min but only 20 min of the 60 min budget are left
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
..............................                                           [100%]
30 passed in 0.09s
```

`tests/test_care_task.py` covers the data classes (priority ranking, sort ordering, input
validation). `tests/test_scheduler.py` covers the scheduling behaviors that matter: priority
ordering, duration tie-breaks, the time budget, skip reasons, clock arithmetic, and the
explanation output.

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `CareTask.priority_score()`, `CareTask.sort_key()`, `Scheduler._sort_tasks()` | Highest priority first, then shortest duration, then title. The title tie-break makes the plan deterministic and testable. |
| Filtering | `Owner.has_capacity_for()`, `Owner.skip_low_priority` | A task that doesn't fit is skipped with a reason, and the loop **continues** — a shorter task later in the list can still fit. The owner can also drop all low-priority tasks outright. |
| Conflict handling | `Scheduler._advance_time()` | Tasks are laid end-to-end from `Owner.day_start`, so slots can't overlap by construction. Wraps correctly across hour boundaries. |
| Recurring tasks | `CareTask.recurrence` | Stored (`daily` / `weekly`) but not yet acted on — the planner builds a single day. This is the clearest next feature. |
| Explanation | `Scheduler.explain()`, `Scheduler._reason_for()` | Returns the strategy, a reason per scheduled task, and a reason per skipped task. |

## 📸 Demo Walkthrough

Run `streamlit run app.py`, then:

1. **Set your constraints in the sidebar.** Enter the owner name, drag "Time available today" to
   60 minutes, set the day to start at `08:00`, and pick `morning` as a preferred window.
2. **Describe the pet.** Enter a name, species, and energy level in the main panel.
3. **Add care tasks.** For each one give a title, duration, priority, category, and preferred time,
   then click **Add task**. They collect in a table below. Add a high-priority 30-min walk, a
   high-priority 10-min feeding, and a low-priority 45-min grooming.
4. **Click Generate schedule.** The plan appears as a table of clock times — feeding at 08:00,
   the walk at 08:10 — because within equal priority the scheduler runs the shorter task first.
5. **Read the skip warning.** Grooming shows up in an amber box explaining it needed 45 minutes
   but only 20 were left in the budget.
6. **Open "Why this plan?"** to see the full reasoning: the strategy line, a justification for each
   scheduled task (including the preferred-window match), and the reason for each skip.
7. **Try the "Skip low-priority tasks today" checkbox** and regenerate to see the reason for
   dropping grooming change from a time constraint to an owner preference.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
