import streamlit as st

from pawpal_system import Owner, Pet, Scheduler, Task

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")
st.caption(
    "A pet care planning assistant. Add your pets and their tasks, set your "
    "constraints, and get a daily plan across all of them."
)

# --- Owner constraints live in the sidebar -----------------------------------

st.sidebar.header("Your day")
owner_name = st.sidebar.text_input("Owner name", value="Jordan")
available_minutes = st.sidebar.slider(
    "Time available today (minutes)", min_value=0, max_value=480, value=100, step=5
)
day_start = st.sidebar.text_input("Start the day at (HH:MM)", value="07:30")
preferred_times = st.sidebar.multiselect(
    "Preferred windows", ["morning", "afternoon", "evening"], default=["morning"]
)
skip_low_priority = st.sidebar.checkbox("Skip low-priority tasks today", value=False)

# --- Pets --------------------------------------------------------------------

# Pets are kept as plain dicts in session state and turned into real objects
# only when the plan is built, so a validation error never corrupts the form.
if "pets" not in st.session_state:
    st.session_state.pets = [
        {"name": "Mochi", "species": "cat", "breed": "Tabby", "energy_level": "medium"},
        {
            "name": "Biscuit",
            "species": "dog",
            "breed": "Golden Retriever",
            "energy_level": "high",
        },
    ]
if "tasks" not in st.session_state:
    st.session_state.tasks = []

st.subheader("Your pets")

with st.form("add_pet", clear_on_submit=True):
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)
    with pcol1:
        new_pet_name = st.text_input("Name")
    with pcol2:
        new_species = st.selectbox("Species", ["dog", "cat", "other"])
    with pcol3:
        new_breed = st.text_input("Breed")
    with pcol4:
        new_energy = st.selectbox("Energy", ["low", "medium", "high"], index=1)

    if st.form_submit_button("Add pet"):
        existing = {p["name"] for p in st.session_state.pets}
        if not new_pet_name.strip():
            st.warning("Give the pet a name.")
        elif new_pet_name.strip() in existing:
            st.warning(f"You already have a pet named {new_pet_name.strip()}.")
        else:
            st.session_state.pets.append(
                {
                    "name": new_pet_name.strip(),
                    "species": new_species,
                    "breed": new_breed,
                    "energy_level": new_energy,
                }
            )

if st.session_state.pets:
    st.table(st.session_state.pets)
    remove_target = st.selectbox(
        "Remove a pet", ["—"] + [p["name"] for p in st.session_state.pets]
    )
    if st.button("Remove") and remove_target != "—":
        st.session_state.pets = [
            p for p in st.session_state.pets if p["name"] != remove_target
        ]
        st.session_state.tasks = [
            t for t in st.session_state.tasks if t["pet"] != remove_target
        ]
else:
    st.info("Add at least one pet to get started.")

st.divider()

# --- Tasks -------------------------------------------------------------------

st.subheader("Care tasks")

if not st.session_state.pets:
    st.info("Add a pet first, then you can give it tasks.")
else:
    st.caption(
        "Leave the fixed time blank to let the scheduler decide when a task "
        "happens. Set one to pin the task to an exact time."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        task_pet = st.selectbox("Pet", [p["name"] for p in st.session_state.pets])
    with col2:
        description = st.text_input("Description", value="Morning walk")
    with col3:
        duration = st.number_input(
            "Duration (minutes)", min_value=1, max_value=240, value=30
        )

    col4, col5, col6 = st.columns(3)
    with col4:
        priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
    with col5:
        category = st.selectbox(
            "Category", ["walk", "feeding", "meds", "enrichment", "grooming", "other"]
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

    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("Add task"):
            st.session_state.tasks.append(
                {
                    "pet": task_pet,
                    "description": description,
                    "duration_minutes": int(duration),
                    "priority": priority,
                    "category": category,
                    "preferred_time": preferred_time,
                    "frequency": frequency,
                    "fixed_time": fixed_time.strip() or None,
                    "completed": False,
                }
            )
    with col_clear:
        if st.button("Clear all tasks"):
            st.session_state.tasks = []

if st.session_state.tasks:
    st.caption("Tick a task off once it's done and it drops out of the plan.")
    for i, task in enumerate(st.session_state.tasks):
        pin = f" @ {task['fixed_time']}" if task["fixed_time"] else ""
        st.session_state.tasks[i]["completed"] = st.checkbox(
            f"**{task['description']}** for {task['pet']} — "
            f"{task['duration_minutes']} min, {task['priority']} priority{pin}",
            value=task["completed"],
            key=f"done_{i}",
        )
else:
    st.info("No tasks yet.")

st.divider()

# --- Plan --------------------------------------------------------------------

st.subheader("Daily plan")

if st.button("Generate schedule", type="primary"):
    if not st.session_state.tasks:
        st.warning("Add at least one task first.")
    else:
        try:
            pets = {}
            for spec in st.session_state.pets:
                pets[spec["name"]] = Pet(**spec)
            for spec in st.session_state.tasks:
                fields = {k: v for k, v in spec.items() if k != "pet"}
                pets[spec["pet"]].add_task(Task(**fields))

            owner = Owner(
                name=owner_name,
                available_minutes=int(available_minutes),
                day_start=day_start,
                preferred_times=preferred_times,
                skip_low_priority=skip_low_priority,
                pets=list(pets.values()),
            )
        except (ValueError, TypeError) as err:
            st.error(f"Check your inputs: {err}")
        else:
            scheduler = Scheduler(owner)
            plan = scheduler.build_plan()

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

            with st.expander("Per pet", expanded=False):
                for pet in owner.pets:
                    slots = scheduler.tasks_for(pet.name)
                    minutes = sum(s["duration_minutes"] for s in slots)
                    st.markdown(f"**{pet.name}** — {len(slots)} task(s), {minutes} min")
                    for slot in slots:
                        st.text(f"  {slot['start_time']}  {slot['description']}")

            with st.expander("Why this plan?", expanded=True):
                for line in scheduler.explain():
                    st.text(line)
