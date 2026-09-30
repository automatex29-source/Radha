"""Sends email (password reset links) through a free provider's HTTPS API.

Set ONE of these on the server:
  BREVO_API_KEY   free at https://www.brevo.com (300 emails/day). MAIL_FROM must be a sender
                  address you verified in Brevo (your own Gmail works, no domain needed).
  RESEND_API_KEY  free at https://resend.com (100 emails/day). Sends to any address only after
                  you verify a domain there; MAIL_FROM must use that domain.

HTTPS is used rather than SMTP because free hosts such as Render block outgoing SMTP ports.
"""
import logging
import os

import httpx

logger = logging.getLogger("radha.mail")

APP_NAME = "Krish AI"


def _sender() -> str:
    return (os.environ.get("MAIL_FROM") or "").strip()


def provider() -> str | None:
    if os.environ.get("BREVO_API_KEY"):
        return "brevo"
    if os.environ.get("RESEND_API_KEY"):
        return "resend"
    return None


def configured() -> bool:
    # Resend has a shared test sender; Brevo needs the address you verified.
    p = provider()
    return p == "resend" or (p == "brevo" and bool(_sender()))


async def send(to: str, subject: str, html: str, text: str) -> None:
    """Send one email. Raises RuntimeError with a readable reason on failure."""
    p = provider()
    sender = _sender()
    async with httpx.AsyncClient(timeout=20) as client:
        if p == "brevo":
            r = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json"},
                json={
                    "sender": {"name": APP_NAME, "email": sender},
                    "to": [{"email": to}],
                    "subject": subject,
                    "htmlContent": html,
                    "textContent": text,
                },
            )
        elif p == "resend":
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                json={
                    "from": f"{APP_NAME} <{sender or 'onboarding@resend.dev'}>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
        else:
            raise RuntimeError("No email provider is set up")
    if r.status_code >= 300:
        logger.error("Email via %s failed (%s): %s", p, r.status_code, r.text[:500])
        raise RuntimeError(f"Email provider {p} returned {r.status_code}")


def reset_email(name: str, link: str, minutes: int) -> tuple[str, str, str]:
    """Subject, HTML and plain-text bodies for a password reset email."""
    subject = f"Reset your {APP_NAME} password"
    greeting = f"Hi {name}," if name else "Hi,"
    text = (
        f"{greeting}\n\nSomeone asked to reset the password for your {APP_NAME} account. "
        f"Open this link to choose a new one (it works once, for {minutes} minutes):\n\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email. Your password stays the same.\n\n"
        "EmpireX"
    )
    html = f"""<!doctype html><html><body style="margin:0;background:#f4f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#151a28">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border-radius:16px;padding:32px">
<tr><td style="font-size:22px;font-weight:800;letter-spacing:-0.5px">Krish <span style="color:#6366f1">AI</span></td></tr>
<tr><td style="padding-top:20px;font-size:16px;line-height:1.6">{greeting}<br><br>Someone asked to reset the password for your {APP_NAME} account. Tap the button to choose a new one.</td></tr>
<tr><td style="padding:28px 0"><a href="{link}" style="display:inline-block;background:#5053ee;color:#ffffff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 28px;border-radius:12px">Reset password</a></td></tr>
<tr><td style="font-size:13px;line-height:1.6;color:#5b6275">This link works once and expires in {minutes} minutes. If you didn't ask for this, ignore this email and your password stays the same.<br><br>Button not working? Paste this into your browser:<br><a href="{link}" style="color:#5053ee;word-break:break-all">{link}</a></td></tr>
</table>
<p style="font-size:12px;color:#8a90a2;margin-top:16px">EmpireX</p>
</td></tr></table></body></html>"""
    return subject, html, text
