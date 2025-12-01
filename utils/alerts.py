# utils/alerts.py
import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_EMAIL = os.getenv("ALERT_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL")


def send_alert(subject, body, attachments=None):
    """
    Send an email alert with optional file attachments.

    Automatically handles SSL/TLS connections based on the configured SMTP port.
    Uses SMTP_SSL for port 465, and auto-detects STARTTLS support for other ports.

    Args:
        subject (str): Email subject line
        body (str): Email body content
        attachments (list, optional): List of file paths to attach to the email.
            Files are attached as application/octet-stream. Defaults to None.

    Returns:
        None

    Raises:
        Prints error messages to stdout if attachment or SMTP operations fail,
        but does not raise exceptions.

    Note:
        Requires SMTP_HOST, SMTP_PORT, FROM_EMAIL, ALERT_EMAIL, SMTP_USER,
        and SMTP_PASS to be configured in the module scope.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ALERT_EMAIL
    msg.set_content(body)

    if attachments:
        for file_path in attachments:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                msg.add_attachment(
                    data,
                    maintype="application",
                    subtype="octet-stream",
                    filename=os.path.basename(file_path),
                )
            except Exception as e:
                print(f"Failed to attach {file_path}: {e}")

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                if SMTP_USER and SMTP_PASS:
                    server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
                return

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()

            if server.has_extn("starttls"):
                try:
                    server.starttls()
                    server.ehlo()
                except:
                    pass

            if SMTP_USER and SMTP_PASS:
                try:
                    server.login(SMTP_USER, SMTP_PASS)
                except Exception as e:
                    print("Login not supported:", e)

            server.send_message(msg)

    except Exception as e:
        print("SMTP ERROR:", e)
