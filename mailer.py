import smtplib
from email.message import EmailMessage
from pathlib import Path
from config import settings

def send_file(subject: str, body: str, file_path: Path) -> None:
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS and settings.REPORT_EMAILS):
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = settings.REPORT_EMAILS
    msg.set_content(body)

    data = file_path.read_bytes()
    msg.add_attachment(data, maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       filename=file_path.name)

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as s:
        s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.send_message(msg)
