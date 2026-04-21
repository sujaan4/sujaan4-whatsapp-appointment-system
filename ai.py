from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - lets the app start before dependencies are installed
    OpenAI = None


STATE_NEW = "NEW"
STATE_ASK_NAME = "ASK_NAME"
STATE_ASK_REQUIREMENT = "ASK_REQUIREMENT"
STATE_ASK_APPOINTMENT = "ASK_APPOINTMENT"
STATE_CONFIRMED = "CONFIRMED"

QUESTION_HINTS = (
    "what",
    "when",
    "where",
    "which",
    "who",
    "how",
    "can",
    "do",
    "does",
    "is",
    "are",
    "price",
    "cost",
    "fees",
    "timing",
    "hours",
    "location",
    "address",
    "available",
)

GREETINGS = {
    "hi",
    "hii",
    "hiii",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
}

RESET_COMMANDS = {
    "reset",
    "restart",
    "start over",
    "new booking",
    "book again",
}

RESCHEDULE_HINTS = (
    "reschedule",
    "change time",
    "change my appointment",
    "different time",
    "different slot",
    "another time",
    "move my appointment",
)

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_openai_client: OpenAI | None = None


@dataclass
class ConversationResult:
    reply: str
    updates: dict[str, Any]


@dataclass
class AppointmentParseResult:
    value: str | None
    clarification: str | None = None


def get_business_timezone() -> ZoneInfo:
    timezone_name = os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("UTC")


def now_local() -> datetime:
    return datetime.now(get_business_timezone())


def get_business_context() -> dict[str, str]:
    return {
        "business_name": os.getenv("BUSINESS_NAME", "Your Business"),
        "business_type": os.getenv("BUSINESS_TYPE", "service business"),
        "business_location": os.getenv("BUSINESS_LOCATION", ""),
        "business_hours": os.getenv("BUSINESS_HOURS", ""),
        "business_timezone": os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata"),
        "contact_person": os.getenv("BUSINESS_CONTACT_PERSON", "our team"),
    }


def get_openai_client() -> OpenAI | None:
    global _openai_client

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None

    if _openai_client is None:
        _openai_client = OpenAI(api_key=api_key)

    return _openai_client


def openai_text(instructions: str, prompt: str, fallback: str, max_output_tokens: int = 180) -> str:
    client = get_openai_client()
    if client is None:
        return fallback

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            instructions=instructions,
            input=prompt,
            max_output_tokens=max_output_tokens,
        )
        text = (getattr(response, "output_text", "") or "").strip()
        return text or fallback
    except Exception:
        return fallback


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_name(raw_name: str) -> str | None:
    candidate = re.sub(r"[^A-Za-z '\-]", "", raw_name).strip(" .,-")
    candidate = " ".join(candidate.split())
    if not candidate:
        return None

    if candidate.lower() in GREETINGS:
        return None

    parts = candidate.split()
    if not 1 <= len(parts) <= 4:
        return None

    if len(candidate) < 2:
        return None

    return " ".join(part.capitalize() for part in parts)


def extract_name(message_text: str) -> str | None:
    message = compact_text(message_text)
    lowered = message.lower()

    patterns = [
        r"(?:my name is|name is|i am|i'm|this is)\s+([a-zA-Z][a-zA-Z '\-]{1,40})",
        r"^([a-zA-Z][a-zA-Z '\-]{1,40})$",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        original_slice = message[match.start(1):match.end(1)]
        clean = clean_name(original_slice)
        if clean:
            return clean

    return None


def looks_like_question(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    if not lowered:
        return False

    if "?" in lowered:
        return True

    if any(lowered.startswith(prefix) for prefix in QUESTION_HINTS):
        return True

    return any(hint in lowered for hint in ("price", "cost", "fees", "location", "timing", "hours"))


def is_reset_command(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    return lowered in RESET_COMMANDS


def is_reschedule_request(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    return any(hint in lowered for hint in RESCHEDULE_HINTS)


def looks_like_requirement(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    if len(lowered) < 4 or looks_like_question(lowered):
        return False

    generic_values = {"yes", "no", "ok", "okay", "appointment", "book", "booking", "service"}
    return lowered not in generic_values


def has_explicit_time_reference(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    return bool(
        re.search(
            r"(\b\d{1,2}:\d{2}\s*(am|pm)?\b)|(\b\d{1,2}\s*(am|pm)\b)|(\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b)",
            lowered,
        )
    )


def has_explicit_date_reference(message_text: str) -> bool:
    lowered = compact_text(message_text).lower()
    if re.search(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", lowered):
        return True
    if re.search(r"\b\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", lowered):
        return True
    if any(word in lowered for word in ("today", "tomorrow", "day after tomorrow", "next ")):
        return True
    return any(day in lowered for day in WEEKDAYS)


def parse_time_component(message_text: str) -> tuple[int, int] | None:
    base = now_local().replace(hour=9, minute=0, second=0, microsecond=0)
    try:
        parsed = date_parser.parse(message_text, fuzzy=True, default=base)
    except (ValueError, OverflowError):
        return None

    return parsed.hour, parsed.minute


def parse_with_relative_date(message_text: str) -> datetime | None:
    lowered = compact_text(message_text).lower()
    if not has_explicit_time_reference(lowered):
        return None

    now = now_local()
    time_parts = parse_time_component(lowered)
    if time_parts is None:
        return None

    if "day after tomorrow" in lowered:
        target_date = now.date() + timedelta(days=2)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            time_parts[0],
            time_parts[1],
            tzinfo=now.tzinfo,
        )

    if "tomorrow" in lowered:
        target_date = now.date() + timedelta(days=1)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            time_parts[0],
            time_parts[1],
            tzinfo=now.tzinfo,
        )

    if "today" in lowered:
        target_date = now.date()
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            time_parts[0],
            time_parts[1],
            tzinfo=now.tzinfo,
        )

    for weekday_name, weekday_number in WEEKDAYS.items():
        if weekday_name not in lowered:
            continue
        days_ahead = (weekday_number - now.weekday()) % 7
        if days_ahead == 0 or f"next {weekday_name}" in lowered:
            days_ahead = days_ahead or 7
        target_date = now.date() + timedelta(days=days_ahead)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            time_parts[0],
            time_parts[1],
            tzinfo=now.tzinfo,
        )

    return None


def parse_appointment_locally(message_text: str) -> AppointmentParseResult:
    text = compact_text(message_text)
    if not has_explicit_time_reference(text):
        return AppointmentParseResult(
            value=None,
            clarification="Please share both the date and time. Example: 24 Apr at 5:30 PM.",
        )

    local_dt = parse_with_relative_date(text)
    if local_dt is None:
        default_dt = now_local().replace(second=0, microsecond=0)
        try:
            local_dt = date_parser.parse(text, fuzzy=True, default=default_dt)
        except (ValueError, OverflowError):
            local_dt = None

        if local_dt is not None:
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=now_local().tzinfo)
            else:
                local_dt = local_dt.astimezone(get_business_timezone())

            if not has_explicit_date_reference(text):
                if local_dt <= now_local():
                    local_dt = local_dt + timedelta(days=1)

    if local_dt is None:
        return AppointmentParseResult(
            value=None,
            clarification="I couldn't read that appointment time. Please send it like `24 Apr 2026 5:30 PM`.",
        )

    if local_dt <= now_local():
        return AppointmentParseResult(
            value=None,
            clarification="Please share a future date and time for the appointment.",
        )

    appointment_value = local_dt.strftime("%Y-%m-%d %H:%M")
    return AppointmentParseResult(value=appointment_value)


def parse_json_object(raw_text: str) -> dict[str, Any] | None:
    if not raw_text:
        return None

    cleaned = raw_text.strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def parse_appointment_with_ai(message_text: str) -> AppointmentParseResult:
    client = get_openai_client()
    if client is None:
        return AppointmentParseResult(value=None)

    instructions = (
        "You extract appointment date and time from WhatsApp messages. "
        "Return valid JSON only. Do not add markdown."
    )
    prompt = f"""
Current local datetime: {now_local().strftime("%Y-%m-%d %H:%M")}
Timezone: {os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")}
User message: {message_text}

Return this exact JSON shape:
{{
  "appointment_datetime": "YYYY-MM-DD HH:MM" or null,
  "needs_clarification": true or false,
  "clarification_prompt": "short text"
}}

Rules:
- Only return a future date and time.
- If the message is ambiguous or missing a clear date or time, set appointment_datetime to null.
- Keep clarification_prompt short and practical.
"""
    fallback = ""
    raw = openai_text(instructions=instructions, prompt=prompt, fallback=fallback, max_output_tokens=120)
    payload = parse_json_object(raw)
    if not payload:
        return AppointmentParseResult(value=None)

    appointment_value = payload.get("appointment_datetime")
    clarification = payload.get("clarification_prompt") or None
    if isinstance(appointment_value, str) and appointment_value.strip():
        return AppointmentParseResult(value=appointment_value.strip())

    return AppointmentParseResult(value=None, clarification=clarification)


def parse_appointment(message_text: str) -> AppointmentParseResult:
    local_result = parse_appointment_locally(message_text)
    if local_result.value:
        return local_result

    ai_result = parse_appointment_with_ai(message_text)
    if ai_result.value:
        return ai_result

    return local_result if local_result.clarification else AppointmentParseResult(
        value=None,
        clarification="Please share the appointment in this format: `24 Apr at 5:30 PM`.",
    )


def format_appointment_for_reply(appointment_value: str | None) -> str:
    if not appointment_value:
        return "your selected time"

    try:
        parsed = datetime.strptime(appointment_value, "%Y-%m-%d %H:%M")
        return parsed.strftime("%d %b %Y at %I:%M %p")
    except ValueError:
        return appointment_value


def render_reply(
    stage: str,
    lead: dict[str, Any],
    latest_message: str,
    fallback: str,
    goal: str,
) -> str:
    business = get_business_context()
    instructions = (
        "You are a WhatsApp booking assistant for a small business. "
        "Write one concise reply in under 70 words. "
        "Be warm, clear, and professional. "
        "Never invent pricing, medical claims, or confirmed availability. "
        "If information is missing, ask only for the next required detail."
    )
    prompt = f"""
Business context:
{json.dumps(business, indent=2)}

Conversation stage: {stage}
Goal: {goal}
Known lead:
{json.dumps(
    {
        "name": lead.get("name"),
        "phone": lead.get("phone"),
        "requirement": lead.get("requirement"),
        "appointment_datetime": lead.get("appointment_datetime"),
    },
    indent=2,
)}
Latest user message: {latest_message or "[empty message]"}
"""
    return openai_text(instructions=instructions, prompt=prompt, fallback=fallback)


def answer_unknown_query(lead: dict[str, Any], question: str, next_step: str) -> str:
    business = get_business_context()
    fallback = f"{next_step}"
    if business["business_hours"]:
        fallback = f"Our team can help with that. Business hours: {business['business_hours']}. {next_step}"

    instructions = (
        "You answer WhatsApp lead questions for a small business. "
        "Reply briefly and then guide the customer back to the booking flow. "
        "If business-specific details are missing, say the team will confirm them."
    )
    prompt = f"""
Business context:
{json.dumps(business, indent=2)}

Known lead:
{json.dumps(
    {
        "name": lead.get("name"),
        "requirement": lead.get("requirement"),
        "appointment_datetime": lead.get("appointment_datetime"),
    },
    indent=2,
)}

Customer question: {question}
Required next step: {next_step}
"""
    return openai_text(instructions=instructions, prompt=prompt, fallback=fallback)


def handle_message(lead: dict[str, Any], message_text: str) -> ConversationResult:
    state = lead.get("conversation_state") or STATE_NEW
    text = compact_text(message_text)

    if is_reset_command(text):
        reset_updates = {
            "name": None,
            "requirement": None,
            "appointment_datetime": None,
            "conversation_state": STATE_ASK_NAME,
            "lead_status": "engaged",
            "last_user_message": text,
        }
        fallback = f"Sure, let's start again. What is your name?"
        reply = render_reply(
            stage="reset",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Restart the booking flow and ask for the customer's name.",
        )
        reset_updates["last_bot_message"] = reply
        return ConversationResult(reply=reply, updates=reset_updates)

    if not text:
        fallback = "I can help with bookings here. Please send a message so I can assist you."
        reply = render_reply(
            stage="empty_message",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Ask the customer to send a message so the booking flow can continue.",
        )
        return ConversationResult(
            reply=reply,
            updates={"lead_status": "engaged", "last_user_message": text, "last_bot_message": reply},
        )

    if state == STATE_NEW:
        extracted_name = extract_name(text)
        if extracted_name:
            new_lead = {**lead, "name": extracted_name}
            fallback = f"Nice to meet you, {extracted_name}. What service or requirement would you like help with?"
            reply = render_reply(
                stage="ask_requirement",
                lead=new_lead,
                latest_message=text,
                fallback=fallback,
                goal="Acknowledge the name and ask for the customer's requirement.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "name": extracted_name,
                    "conversation_state": STATE_ASK_REQUIREMENT,
                    "lead_status": "qualified",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        if looks_like_question(text):
            reply = answer_unknown_query(
                lead=lead,
                question=text,
                next_step="To begin the booking, please share your name.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "conversation_state": STATE_ASK_NAME,
                    "lead_status": "engaged",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        fallback = f"Hi! Welcome to {get_business_context()['business_name']}. I can help you book an appointment. What is your name?"
        reply = render_reply(
            stage="welcome_ask_name",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Greet the customer and ask for their name.",
        )
        return ConversationResult(
            reply=reply,
            updates={
                "conversation_state": STATE_ASK_NAME,
                "lead_status": "engaged",
                "last_user_message": text,
                "last_bot_message": reply,
            },
        )

    if state == STATE_ASK_NAME:
        extracted_name = extract_name(text)
        if extracted_name:
            new_lead = {**lead, "name": extracted_name}
            fallback = f"Thanks, {extracted_name}. What service or requirement would you like to book?"
            reply = render_reply(
                stage="ask_requirement",
                lead=new_lead,
                latest_message=text,
                fallback=fallback,
                goal="Thank the customer and ask for the service requirement.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "name": extracted_name,
                    "conversation_state": STATE_ASK_REQUIREMENT,
                    "lead_status": "qualified",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        if looks_like_question(text):
            reply = answer_unknown_query(
                lead=lead,
                question=text,
                next_step="Please share your name so I can continue the booking.",
            )
            return ConversationResult(
                reply=reply,
                updates={"last_user_message": text, "last_bot_message": reply},
            )

        fallback = "Please share your full name so I can continue with your booking."
        reply = render_reply(
            stage="ask_name_retry",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Ask again for the customer's name.",
        )
        return ConversationResult(
            reply=reply,
            updates={"last_user_message": text, "last_bot_message": reply},
        )

    if state == STATE_ASK_REQUIREMENT:
        if looks_like_question(text):
            reply = answer_unknown_query(
                lead=lead,
                question=text,
                next_step="Please tell me what service or help you need.",
            )
            return ConversationResult(
                reply=reply,
                updates={"last_user_message": text, "last_bot_message": reply},
            )

        if looks_like_requirement(text):
            new_lead = {**lead, "requirement": text}
            fallback = "Please share your preferred appointment date and time. Example: 24 Apr at 5:30 PM."
            reply = render_reply(
                stage="ask_appointment",
                lead=new_lead,
                latest_message=text,
                fallback=fallback,
                goal="Ask for the preferred appointment date and time.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "requirement": text,
                    "conversation_state": STATE_ASK_APPOINTMENT,
                    "lead_status": "qualified",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        fallback = "Please tell me what service you want to book, for example: dental checkup, haircut, or maths coaching."
        reply = render_reply(
            stage="ask_requirement_retry",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Ask again for the service requirement.",
        )
        return ConversationResult(
            reply=reply,
            updates={"last_user_message": text, "last_bot_message": reply},
        )

    if state == STATE_ASK_APPOINTMENT:
        if looks_like_question(text):
            reply = answer_unknown_query(
                lead=lead,
                question=text,
                next_step="Please share your preferred appointment date and time.",
            )
            return ConversationResult(
                reply=reply,
                updates={"last_user_message": text, "last_bot_message": reply},
            )

        appointment = parse_appointment(text)
        if appointment.value:
            formatted_time = format_appointment_for_reply(appointment.value)
            new_lead = {**lead, "appointment_datetime": appointment.value}
            fallback = (
                f"Your booking request is confirmed for {formatted_time}. "
                f"We have saved your details and our team will contact you shortly."
            )
            reply = render_reply(
                stage="confirm_booking",
                lead=new_lead,
                latest_message=text,
                fallback=fallback,
                goal="Confirm the appointment and summarize the booking clearly.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "appointment_datetime": appointment.value,
                    "conversation_state": STATE_CONFIRMED,
                    "lead_status": "booked",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        fallback = appointment.clarification or "Please send the appointment like `24 Apr at 5:30 PM`."
        reply = render_reply(
            stage="ask_appointment_retry",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Ask again for a clear appointment date and time.",
        )
        return ConversationResult(
            reply=reply,
            updates={"last_user_message": text, "last_bot_message": reply},
        )

    if state == STATE_CONFIRMED:
        if is_reschedule_request(text):
            fallback = "Sure, please share the new appointment date and time you prefer."
            reply = render_reply(
                stage="reschedule",
                lead=lead,
                latest_message=text,
                fallback=fallback,
                goal="Ask for a new appointment date and time so the booking can be rescheduled.",
            )
            return ConversationResult(
                reply=reply,
                updates={
                    "conversation_state": STATE_ASK_APPOINTMENT,
                    "lead_status": "qualified",
                    "last_user_message": text,
                    "last_bot_message": reply,
                },
            )

        if looks_like_question(text):
            reply = answer_unknown_query(
                lead=lead,
                question=text,
                next_step="If you'd like to change your booking, send a new date and time.",
            )
            return ConversationResult(
                reply=reply,
                updates={"last_user_message": text, "last_bot_message": reply},
            )

        fallback = (
            f"Your appointment request is already saved for "
            f"{format_appointment_for_reply(lead.get('appointment_datetime'))}. "
            f"If you want to reschedule, send a new date and time."
        )
        reply = render_reply(
            stage="already_confirmed",
            lead=lead,
            latest_message=text,
            fallback=fallback,
            goal="Remind the customer their booking is saved and explain how to reschedule.",
        )
        return ConversationResult(
            reply=reply,
            updates={"last_user_message": text, "last_bot_message": reply},
        )

    fallback = "I can help you with booking an appointment. Please share your name to continue."
    reply = render_reply(
        stage="fallback",
        lead=lead,
        latest_message=text,
        fallback=fallback,
        goal="Recover the booking flow and ask for the customer's name.",
    )
    return ConversationResult(
        reply=reply,
        updates={
            "conversation_state": STATE_ASK_NAME,
            "lead_status": "engaged",
            "last_user_message": text,
            "last_bot_message": reply,
        },
    )
