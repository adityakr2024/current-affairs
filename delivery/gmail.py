"""
delivery/gmail.py — Send The Currents PDFs via Gmail SMTP.
"""
from __future__ import annotations
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def send_email(sender: str, app_password: str, recipient: str,
               subject: str, body: str,
               attachment_paths: list | None = None) -> bool:
    """Send email with optional PDF attachments (list of Paths) via Gmail SMTP."""
    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    for path in (attachment_paths or []):
        if not path or not Path(path).exists():
            continue
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={Path(path).name}"
        )
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, app_password)
        server.send_message(msg)

    return True
