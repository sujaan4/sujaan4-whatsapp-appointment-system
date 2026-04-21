from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from db import add_manual_lead, get_dashboard_metrics, init_db, list_appointments, list_leads


def format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return parsed.strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return value


init_db()

st.set_page_config(page_title="WhatsApp Lead Dashboard", layout="wide")
st.title("WhatsApp Appointment & Lead Dashboard")
st.caption("Track WhatsApp leads, monitor bookings, and add walk-in or phone leads manually.")

with st.sidebar:
    st.header("Filters")
    search_term = st.text_input("Search by name, phone, or requirement")
    status_filter = st.selectbox("Lead status", ["All", "new", "engaged", "qualified", "booked"])
    source_filter = st.selectbox("Source", ["All", "whatsapp", "manual"])
    upcoming_only = st.checkbox("Show only upcoming appointments", value=False)
    if st.button("Refresh data", use_container_width=True):
        st.rerun()

metrics = get_dashboard_metrics()
metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
metric_col_1.metric("Total Leads", metrics["total_leads"])
metric_col_2.metric("Booked Appointments", metrics["booked_appointments"])
metric_col_3.metric("Pending Leads", metrics["pending_leads"])
metric_col_4.metric("WhatsApp Leads", metrics["whatsapp_leads"])

leads = list_leads(search=search_term, lead_status=status_filter, source=source_filter)

if upcoming_only:
    now_marker = datetime.now().strftime("%Y-%m-%d %H:%M")
    leads = [
        lead
        for lead in leads
        if lead.get("appointment_datetime") and lead["appointment_datetime"] >= now_marker
    ]

st.subheader("All Leads")
lead_rows = [
    {
        "Name": lead.get("name") or lead.get("profile_name") or "-",
        "Phone": lead.get("phone"),
        "Requirement": lead.get("requirement") or "-",
        "Appointment": format_datetime(lead.get("appointment_datetime")),
        "Status": lead.get("lead_status"),
        "State": lead.get("conversation_state"),
        "Source": lead.get("source"),
        "Updated": lead.get("updated_at"),
    }
    for lead in leads
]

if lead_rows:
    st.dataframe(lead_rows, use_container_width=True, hide_index=True)
else:
    st.info("No leads match the current filters.")

st.subheader("Appointment View")
appointments = list_appointments(search=search_term, upcoming_only=upcoming_only)
if status_filter.lower() != "all":
    appointments = [item for item in appointments if item.get("lead_status") == status_filter.lower()]
if source_filter.lower() != "all":
    appointments = [item for item in appointments if item.get("source") == source_filter.lower()]

appointment_rows = [
    {
        "Customer": item.get("name") or item.get("profile_name") or "-",
        "Phone": item.get("phone"),
        "Requirement": item.get("requirement") or "-",
        "Appointment": format_datetime(item.get("appointment_datetime")),
        "Status": item.get("lead_status"),
    }
    for item in appointments
]

if appointment_rows:
    st.dataframe(appointment_rows, use_container_width=True, hide_index=True)
else:
    st.info("No appointments available for the selected filters.")

st.subheader("Add Lead Manually")
with st.form("manual_lead_form", clear_on_submit=True):
    manual_name = st.text_input("Customer name")
    manual_phone = st.text_input("Phone / WhatsApp number")
    manual_requirement = st.text_input("Requirement / service")
    save_with_appointment = st.checkbox("Save with appointment", value=True)

    selected_date = None
    selected_time = None
    if save_with_appointment:
        date_col, time_col = st.columns(2)
        selected_date = date_col.date_input("Appointment date")
        selected_time = time_col.time_input("Appointment time", value=time(hour=10, minute=0))

    submitted = st.form_submit_button("Save lead")

    if submitted:
        if not manual_name.strip() or not manual_phone.strip() or not manual_requirement.strip():
            st.error("Name, phone, and requirement are required.")
        else:
            appointment_value = None
            if save_with_appointment and selected_date and selected_time:
                appointment_value = datetime.combine(selected_date, selected_time).strftime("%Y-%m-%d %H:%M")

            add_manual_lead(
                name=manual_name.strip(),
                phone=manual_phone.strip(),
                requirement=manual_requirement.strip(),
                appointment_datetime=appointment_value,
            )
            st.success("Lead saved successfully.")
            st.rerun()
