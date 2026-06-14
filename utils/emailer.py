import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASS = os.environ.get('SMTP_PASS')
FROM_ADDR = os.environ.get('EMAIL_FROM', SMTP_USER)


def send_email(name, to_addr, subject, body):
    if not SMTP_HOST or not to_addr:
        return False
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = FROM_ADDR
    msg['To'] = to_addr
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            if SMTP_USER and SMTP_PASS:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception:
        return False
