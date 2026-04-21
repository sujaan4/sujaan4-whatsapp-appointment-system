from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from ai import handle_message
from db import get_or_create_lead, init_db, list_leads, log_message, update_lead

load_dotenv()


def normalize_phone(from_value: str | None, waid: str | None) -> str:
    """Create a cleaner phone identifier from Twilio's WhatsApp payload."""
    if waid:
        clean = waid.strip()
        return clean if clean.startswith("+") else f"+{clean}"

    if not from_value:
        return "unknown"

    return from_value.replace("whatsapp:", "").strip()


def twilio_validation_enabled() -> bool:
    return os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() in {"1", "true", "yes"}


def validate_twilio_request() -> bool:
    """Validate webhook requests in production when signature checks are enabled."""
    if not twilio_validation_enabled():
        return True

    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not auth_token:
        return False

    validator = RequestValidator(auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(request.url, request.form, signature)


def build_twilio_response(message: str) -> str:
    response = MessagingResponse()
    response.message(message)
    return str(response)


def create_app() -> Flask:
    init_db()

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.route("/health", methods=["GET"])
    def health() -> tuple[dict[str, str], int]:
        return {
            "status": "ok",
            "service": "whatsapp-appointment-system",
            "signature_validation": str(twilio_validation_enabled()).lower(),
        }, 200

    @app.route("/api/leads", methods=["GET"])
    def api_leads():
        search = request.args.get("search", "")
        lead_status = request.args.get("status", "All")
        source = request.args.get("source", "All")
        return jsonify(list_leads(search=search, lead_status=lead_status, source=source))

    @app.route("/whatsapp", methods=["POST"])
    def whatsapp_webhook() -> str:
        if not validate_twilio_request():
            abort(403, description="Invalid Twilio request signature.")

        incoming_text = (request.values.get("Body") or "").strip()
        profile_name = (request.values.get("ProfileName") or "").strip()
        from_value = request.values.get("From")
        waid = request.values.get("WaId")
        phone = normalize_phone(from_value, waid)

        lead = get_or_create_lead(phone=phone, profile_name=profile_name)

        if incoming_text:
            log_message(phone=phone, direction="incoming", message=incoming_text)

        result = handle_message(lead=lead, message_text=incoming_text)
        update_lead(phone, **result.updates)
        log_message(phone=phone, direction="outgoing", message=result.reply)

        return build_twilio_response(result.reply)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "true").lower() in {"1", "true", "yes"},
    )
