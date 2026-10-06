"""PawPal+ Streamlit UI.

This file holds no scheduling logic. It imports the backend classes, keeps one
live Owner object in the Streamlit session cache, and wires each UI control to
a real method on that object.
"""

import streamlit as st

# 1) Bring the specific classes we need in from the logic layer.
from pawpal_system import Owner, Pet, Scheduler, Task

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")
st.caption(
    "A pet care planning assistant. Add your pets and their tasks, set your "
    "constraints, and get a daily plan across all of them."
)


# --- 2) The session cache ----------------------------------------------------
#
# Streamlit reruns this whole script on every interaction, so anything built at
# module level would be thrown away each time. st.session_state survives those
# reruns, so we check whether the Owner already exists and only build it the
# first time. After that, every click mutates the same live object graph:
# Owner -> Pet -> Task.


def seed_owner():
    """Build the starting Owner, used only on the very first page load."""
    owner = Owner(
        name="Jordan",
        available_minutes=100,
        day_start="07:30",
        preferred_times=["morning", "evening"],
    )
    mochi = owner.add_pet(Pet("Mochi", species="cat", breed="Tabby"))
    biscuit = owner.add_pet(
        Pet("Biscuit", species="dog", breed="Golden Retriever", energy_level="high")
    )
    mochi.add_task(
        Task("Feeding", 10, priority="high", category="feeding", fixed_time="07:30")
    )
    mochi.add_task(Task("Litter box", 10, priority="medium"))
    biscuit.add_task(
        Task("Heartworm meds", 5, priority="high", category="meds", fixed_time="08:00")
    )
    biscuit.add_task(
        Task("Morning walk", 30, priority="high", category="walk",
             preferred_time="morning")
    )
    return owner


if "owner" not in st.session_state:
    st.session_state.owner = seed_owner()
if "scheduler" not in st.session_state:
    # Keeps the last plan on screen across reruns instead of it vanishing the
    # moment you tick a checkbox.
    st.session_state.scheduler = None

owner = st.session_state.owner


# --- 3) Sidebar: each widget calls a validated setter on the live Owner -------

st.sidebar.header("Your day")

name_input = st.sidebar.text_input("Owner name", value=owner.name)
try:
    owner.rename(name_input)
except ValueError:
    st.sidebar.error("Owner name cannot be empty.")

owner.set_available_minutes(
    st.sidebar.slider(
        "Time available today (minutes)",
        min_value=0,
        max_value=480,
        value=owner.available_minutes,
        step=5,
    )
)

day_start_input = st.sidebar.text_input("Start the day at (HH:MM)", value=owner.day_start)
try:
    owner.set_day_start(day_start_input)
except ValueError:
    st.sidebar.error("Start time must look like HH:MM, e.g. 07:30.")

owner.preferred_times = st.sidebar.multiselect(
    "Preferred windows",
    ["morning", "afternoon", "evening"],
    default=owner.preferred_times,
)
owner.skip_low_priority = st.sidebar.checkbox(
    "Skip low-priority tasks today", value=owner.skip_low_priority
)

st.sidebar.divider()
st.sidebar.metric("Pending work", f"{owner.pending_minutes()} min")
if owner.is_overcommitted():
    over = owner.pending_minutes() - owner.available_minutes
    st.sidebar.warning(f"{over} min more than the day allows.")


# --- Pets: Owner.add_pet() / Owner.remove_pet() ------------------------------

st.subheader("Your pets")

with st.form("add_pet", clear_on_submit=True):
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)
    with pcol1:
        new_name = st.text_input("Name")
    with pcol2:
        new_species = st.selectbox("Species", ["dog", "cat", "other"])
    with pcol3:
        new_breed = st.text_input("Breed")
    with pcol4:
        new_energy = st.selectbox("Energy", ["low", "medium", "high"], index=1)

    if st.form_submit_button("Add pet"):
        try:
            # Owner.add_pet raises on a duplicate name, so the UI does not
            # need its own duplicate check.
            owner.add_pet(
                Pet(
                    name=new_name,
                    species=new_species,
                    breed=new_breed,
                    energy_level=new_energy,
                )
            )
        except (ValueError, TypeError) as err:
            st.error(f"Could not add that pet: {err}")

if owner.pets:
    st.table(
        [
            {
                "Name": pet.name,
                "Species": pet.species,
                "Breed": pet.breed,
                "Energy": pet.energy_level,
                "Tasks": len(pet.tasks),
                "Pending min": pet.pending_minutes(),
            }
            for pet in owner.pets
        ]
    )

    rcol1, rcol2 = st.columns([3, 1])
    with rcol1:
        to_remove = st.selectbox("Remove a pet", [p.name for p in owner.pets])
    with rcol2:
        st.write("")
        if st.button("Remove pet"):
            owner.remove_pet(to_remove)  # tasks go with the pet
            st.session_state.scheduler = None
            st.rerun()
else:
    st.info("Add a pet to get started.")

st.divider()


# --- Tasks: Pet.add_task() / Pet.remove_task() / Task.mark_complete() --------

st.subheader("Care tasks")

if not owner.pets:
    st.info("Add a pet first, then you can give it tasks.")
else:
    st.caption(
        "Leave the fixed time blank to let the scheduler decide when a task "
        "happens. Set one to pin the task to an exact time."
    )

    with st.form("add_task", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            task_pet_name = st.selectbox("Pet", [p.name for p in owner.pets])
        with col2:
            description = st.text_input("Description", value="Evening walk")
        with col3:
            duration = st.number_input(
                "Duration (minutes)", min_value=1, max_value=240, value=30
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
        with col5:
            category = st.selectbox(
                "Category",
                ["walk", "feeding", "meds", "enrichment", "grooming", "other"],
            )
        with col6:
            frequency = st.selectbox("Frequency", ["daily", "weekly"])

        col7, col8 = st.columns(2)
        with col7:
            preferred_time = st.selectbox(
                "Preferred window", ["any", "morning", "afternoon", "evening"]
            )
        with col8:
            fixed_time = st.text_input("Fixed time (HH:MM, optional)", value="")

        if st.form_submit_button("Add task"):
            try:
                # Task.__post_init__ validates, so a bad fixed time is caught
                # here and now rather than when the plan is generated.
                new_task = Task(
                    description=description,
                    duration_minutes=int(duration),
                    priority=priority,
                    category=category,
                    preferred_time=preferred_time,
                    frequency=frequency,
                    fixed_time=fixed_time.strip() or None,
                )
                owner.get_pet(task_pet_name).add_task(new_task)
            except (ValueError, TypeError) as err:
                st.error(f"Could not add that task: {err}")

    if owner.all_tasks():
        st.caption("Tick a task off once it's done and it drops out of the plan.")
        for pet in owner.pets:
            if not pet.tasks:
                continue
            st.markdown(f"**{pet.name}**")
            for i, task in enumerate(pet.tasks):
                tcol1, tcol2 = st.columns([6, 1])
                with tcol1:
                    pin = f" @ {task.fixed_time}" if task.is_anchored() else ""
                    done = st.checkbox(
                        f"{task.description} — {task.duration_minutes} min, "
                        f"{task.priority} priority{pin}",
                        value=task.completed,
                        key=f"{pet.name}_{i}_{task.description}",
                    )
                    # Call the real methods rather than assigning the field.
                    task.mark_complete() if done else task.mark_incomplete()
                with tcol2:
                    if st.button("Delete", key=f"del_{pet.name}_{i}_{task.description}"):
                        pet.remove_task(task.description)
                        st.session_state.scheduler = None
                        st.rerun()
    else:
        st.info("No tasks yet.")

st.divider()


# --- The plan: Scheduler.build_plan() and Scheduler.explain() ----------------

st.subheader("Daily plan")

pcol1, pcol2 = st.columns([1, 3])
with pcol1:
    if st.button("Generate schedule", type="primary"):
        scheduler = Scheduler(owner)
        scheduler.build_plan()
        st.session_state.scheduler = scheduler
with pcol2:
    if st.button("Clear plan"):
        st.session_state.scheduler = None

scheduler = st.session_state.scheduler

if scheduler is not None:
    plan = scheduler.scheduled

    if plan:
        st.success(
            f"Planned {len(plan)} task(s) across {len(owner.pets)} pet(s) — "
            f"{scheduler.total_scheduled_minutes()} of "
            f"{owner.available_minutes} minutes used."
        )
        st.table(
            [
                {
                    "Time": slot["start_time"],
                    "Pet": slot["pet"],
                    "Task": slot["description"],
                    "Minutes": slot["duration_minutes"],
                    "Priority": slot["priority"],
                    "Pinned": "yes" if slot["anchored"] else "",
                }
                for slot in plan
            ]
        )
    else:
        st.warning("Nothing could be scheduled with the time available.")

    if scheduler.skipped:
        st.warning(
            "Skipped today:\n\n"
            + "\n".join(
                f"- **{item['description']}** ({item['pet']}) — {item['reason']}"
                for item in scheduler.skipped
            )
        )

    with st.expander("Per pet"):
        for pet in owner.pets:
            slots = scheduler.tasks_for(pet.name)
            minutes = sum(s["duration_minutes"] for s in slots)
            st.markdown(f"**{pet.name}** — {len(slots)} task(s), {minutes} min")
            for slot in slots:
                st.text(f"  {slot['start_time']}  {slot['description']}")

    with st.expander("Why this plan?", expanded=True):
        for line in scheduler.explain():
            st.text(line)
else:
    st.info("Click **Generate schedule** to build today's plan.")
