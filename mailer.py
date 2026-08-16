import os
import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import quote

import config

MERGE_TAG_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class MailError(RuntimeError):
    pass


def render_template(template: str, lead: dict[str, Any]) -> str:
    values = {
        "ownerName": lead.get("owner_name") or lead.get("business_name") or "there",
        "businessName": lead.get("business_name") or "",
        "whatsappNumber": config.WHATSAPP_NUMBER,
        "unsubscribeUrl": unsubscribe_url(lead),
    }
    return MERGE_TAG_RE.sub(lambda match: str(values.get(match.group(1), "")), template)


def unsubscribe_url(lead: dict[str, Any]) -> str:
    email = lead.get("email") or ""
    return f"{config.UNSUBSCRIBE_BASE_URL}?email={quote(email)}"


def build_message(
    lead: dict[str, Any], subject: str, html_template: str, attachment_path: str | None
) -> MIMEMultipart:
    message = MIMEMultipart()
    message["From"] = config.SMTP_EMAIL
    message["To"] = lead["email"]
    message["Subject"] = render_template(subject, lead)
    message.attach(MIMEText(render_template(html_template, lead), "html"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as handle:
            part = MIMEApplication(handle.read(), _subtype="pdf")
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=os.path.basename(attachment_path),
        )
        message.attach(part)
    return message


def open_connection() -> smtplib.SMTP:
    if not config.smtp_configured():
        raise MailError("SMTP_EMAIL / SMTP_PASSWORD are not configured")
    server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
    server.starttls()
    server.login(config.SMTP_EMAIL, config.SMTP_PASSWORD)
    return server


def send_lead(
    server: smtplib.SMTP,
    lead: dict[str, Any],
    subject: str,
    html_template: str,
    attachment_path: str | None,
) -> None:
    if not lead.get("email"):
        raise MailError(f"Lead {lead.get('id')} has no email address")
    message = build_message(lead, subject, html_template, attachment_path)
    server.sendmail(config.SMTP_EMAIL, [lead["email"]], message.as_string())
