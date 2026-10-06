import streamlit as st

from pawpal_system import CareTask, Owner, Pet, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")
st.caption("A pet care planning assistant. Add your tasks, set your constraints, get a daily plan.")

# --- Owner constraints live in the sidebar -----------------------------------

st.sidebar.header("Your day")
owner_name = st.sidebar.text_input("Owner name", value="Jordan")
available_minutes = st.sidebar.slider(
    "Time available today (minutes)", min_value=0, max_value=480, value=60, step=5
)
day_start = st.sidebar.text_input("Start the day at (HH:MM)", value="08:00")
preferred_times = st.sidebar.multiselect(
    "Preferred windows", ["morning", "afternoon", "evening"], default=["morning"]
)
skip_low_priority = st.sidebar.checkbox("Skip low-priority tasks today", value=False)

# --- Pet ---------------------------------------------------------------------

st.subheader("Your pet")
col_a, col_b, col_c = st.columns(3)
with col_a:
    pet_name = st.text_input("Pet name", value="Mochi")
with col_b:
    species = st.selectbox("Species", ["dog", "cat", "other"])
with col_c:
    energy_level = st.selectbox("Energy level", ["low", "medium", "high"], index=1)

# --- Tasks -------------------------------------------------------------------

st.subheader("Care tasks")
st.caption("Add the things that need to happen today. These feed into the scheduler.")

if "tasks" not in st.session_state:
    st.session_state.tasks = []

col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)

col4, col5 = st.columns(2)
with col4:
    category = st.selectbox(
        "Category", ["walk", "feeding", "meds", "enrichment", "grooming", "other"]
    )
with col5:
    preferred_time = st.selectbox(
        "Preferred time", ["any", "morning", "afternoon", "evening"]
    )

col_add, col_clear = st.columns(2)
with col_add:
    if st.button("Add task"):
        st.session_state.tasks.append(
            {
                "title": task_title,
                "duration_minutes": int(duration),
                "priority": priority,
                "category": category,
                "preferred_time": preferred_time,
            }
        )
with col_clear:
    if st.button("Clear all tasks"):
        st.session_state.tasks = []

if st.session_state.tasks:
    st.table(st.session_state.tasks)
else:
    st.info("No tasks yet. Add one above.")

st.divider()

# --- Plan --------------------------------------------------------------------

st.subheader("Daily plan")

if st.button("Generate schedule", type="primary"):
    if not st.session_state.tasks:
        st.warning("Add at least one task first.")
    else:
        try:
            owner = Owner(
                name=owner_name,
                available_minutes=int(available_minutes),
                day_start=day_start,
                preferred_times=preferred_times,
                skip_low_priority=skip_low_priority,
            )
            pet = Pet(
                name=pet_name,
                species=species,
                energy_level=energy_level,
                tasks=[CareTask(**t) for t in st.session_state.tasks],
            )
        except ValueError as err:
            st.error(f"Check your inputs: {err}")
        else:
            scheduler = Scheduler(owner, pet)
            plan = scheduler.build_plan()

            if plan:
                st.success(
                    f"Planned {len(plan)} task(s) for {pet.name} — "
                    f"{scheduler.total_scheduled_minutes()} of "
                    f"{owner.available_minutes} minutes used."
                )
                st.table(
                    [
                        {
                            "Time": slot["start_time"],
                            "Task": slot["title"],
                            "Minutes": slot["duration_minutes"],
                            "Priority": slot["priority"],
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
                        f"- **{item['title']}** — {item['reason']}"
                        for item in scheduler.skipped
                    )
                )

            with st.expander("Why this plan?", expanded=True):
                for line in scheduler.explain():
                    st.text(line)
