"""Friendly, personal emails with a picture at the moments that matter:

- welcome: right after someone signs up (says whose invite gave them free Pro, when it did)
- friend joined: to the person whose invite link was used
- plan started: after a Pro or Max payment goes through

Each one has the person's name in its picture (see invite_card.py) and in the words, three things to try,
and one clear button. They go out only when email is set up (see mailer.py); a failed email never stops
a sign-up or a payment.
"""
import html as _html
import logging
import os
from urllib.parse import quote

import mailer

logger = logging.getLogger("radha.growth_mail")

TRY_FREE = [
    ("Ask anything", "Type a question the way you'd ask a friend, in English, Hindi or Hinglish."),
    ("Talk to the Counsellor", "Share what's on your mind with Krish Robo and get calm, honest advice."),
    ("Make something", "Ask for a slide deck, a study plan, a poster or a small app, and watch it appear."),
]
TRY_PAID = {
    "pro": [
        ("Premium AI models", "Pick a premium model for harder questions, longer writing and sharper code."),
        ("Create much more", "10x the usage of Basic for pictures, decks and app builds, refilled every 5 hours."),
        ("Publish your apps", "Put the apps you build on the web with one tap and share the link."),
    ],
    "max": [
        ("The strongest AI models", "Use every premium model for research, writing and code."),
        ("Create at full speed", "30x the usage of Basic, refilled every 5 hours, for the biggest projects."),
        ("Automate your work", "Up to 30 automations that run on their own and send you the results."),
    ],
}


def _first(name: str) -> str:
    return (name or "").strip().split(" ")[0][:30]


def _layout(picture: str, heading: str, intro: str, tries: list, button: str, link: str, footer: str) -> str:
    rows = "".join(
        f'<tr><td style="padding:0 0 14px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="top" style="padding:2px 12px 0 0"><div style="width:26px;height:26px;border-radius:13px;'
        f'background:#fff0e1;color:#ff8a1e;font-weight:800;font-size:14px;line-height:26px;text-align:center">{i}</div></td>'
        f'<td style="font-size:15px;line-height:1.5"><b>{_html.escape(t)}</b><br>'
        f'<span style="color:#5b6275">{_html.escape(d)}</span></td></tr></table></td></tr>'
        for i, (t, d) in enumerate(tries, 1))
    return f"""<!doctype html><html><body style="margin:0;background:#f4f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#151a28">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden">
<tr><td><img src="{picture}" width="560" alt="{_html.escape(heading)}" style="display:block;width:100%;height:auto;border:0"></td></tr>
<tr><td style="padding:28px 28px 8px">
<h1 style="margin:0 0 12px;font-size:24px;line-height:1.25;letter-spacing:-0.4px">{_html.escape(heading)}</h1>
<p style="margin:0 0 22px;font-size:16px;line-height:1.6;color:#2a3042">{intro}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
<p style="margin:14px 0 26px"><a href="{link}" style="display:inline-block;background:#ff8a1e;color:#ffffff;text-decoration:none;font-weight:800;font-size:16px;padding:14px 30px;border-radius:12px">{_html.escape(button)}</a></p>
<p style="margin:0 0 26px;font-size:13px;line-height:1.6;color:#8a90a2">{footer}</p>
</td></tr></table>
<p style="font-size:12px;color:#8a90a2;margin-top:16px">Krish AI by EmpireX</p>
</td></tr></table></body></html>"""


def _text(heading: str, intro: str, tries: list, link: str) -> str:
    lines = [heading, "", _html.unescape(intro.replace("<b>", "").replace("</b>", "")), ""]
    lines += [f"{i}. {t}: {d}" for i, (t, d) in enumerate(tries, 1)]
    return "\n".join(lines + ["", f"Open Krish AI: {link}", "", "Krish AI by EmpireX"])


def welcome(app_url: str, name: str, inviter_name: str = "", days: int = 0) -> tuple:
    first = _first(name)
    picture = f"{app_url}/api/cards/welcome.png?n={quote(first)}" + ("&p=pro" if inviter_name else "")
    if inviter_name:
        inviter = _html.escape(_first(inviter_name))
        subject = f"{_first(inviter_name)} gave you {days} days of Krish AI Pro 🎁"
        heading = f"Welcome, {first}! Your Pro days have started" if first else "Welcome! Your Pro days have started"
        intro = (f"Thanks to <b>{inviter}</b>'s invite, you have <b>{days} days of Pro, free</b>: premium AI models and "
                 "lots more pictures, decks and apps every day. Here's a good way to start:")
    else:
        subject = f"Welcome to Krish AI, {first} 👋" if first else "Welcome to Krish AI 👋"
        heading = f"Hi {first}, welcome to Krish AI" if first else "Welcome to Krish AI"
        intro = ("Krish is your saarthi for every task: questions, study, writing, planning and building. "
                 "Chat is free and unlimited. Here's a good way to start:")
    footer = ("Tip: invite a friend from the menu in the app. When they join, they get 7 days of Pro, free, and so do you (once).")
    body = _layout(picture, heading, intro, TRY_FREE, "Open Krish AI", app_url, footer)
    return subject, body, _text(heading, intro, TRY_FREE, app_url)


def friend_joined(app_url: str, inviter_name: str, friend_name: str, days: int, rewarded: bool, joined: int) -> tuple:
    first, friend = _first(inviter_name), _first(friend_name) or "Your friend"
    picture = f"{app_url}/api/cards/welcome.png?n={quote(first)}&p=pro"
    if rewarded:
        subject = f"{friend} joined Krish AI: {days} more days of Pro for you 🎉"
        heading = f"{friend} joined with your link!"
        intro = (f"Thank you for spreading the word, {_html.escape(first)}. We've added <b>{days} days of Pro</b> "
                 f"to your account. That's {joined} friend{'s' if joined != 1 else ''} so far.")
    else:
        subject = f"{friend} joined Krish AI with your link"
        heading = f"{friend} joined with your link!"
        intro = (f"Thank you, {_html.escape(first)}. {_html.escape(friend)} now has free Pro days. You've already had "
                 "your one-time free Pro reward for inviting, so this one is a gift to your friend.")
    tries = TRY_PAID["pro"]
    body = _layout(picture, heading, intro, tries, "Use your Pro days", app_url,
                   "Keep sharing: open the menu in Krish AI and tap Invite friends.")
    return subject, body, _text(heading, intro, tries, app_url)


def plan_started(app_url: str, name: str, plan: str, until: str) -> tuple:
    first = _first(name)
    plan_name = "Max" if plan == "max" else "Pro"
    picture = f"{app_url}/api/cards/welcome.png?n={quote(first)}&p={plan}"
    subject = f"You're on Krish AI {plan_name}, {first} ✨" if first else f"You're on Krish AI {plan_name} ✨"
    heading = f"Thank you, {first}. {plan_name} is on!" if first else f"Thank you. {plan_name} is on!"
    intro = (f"Your payment went through and <b>Krish AI {plan_name}</b> is active until <b>{_html.escape(until)}</b>. "
             "With autopay it renews by itself, and you can turn that off any time in Settings &gt; Billing. "
             "Here's what's new for you:")
    tries = TRY_PAID.get(plan, TRY_PAID["pro"])
    body = _layout(picture, heading, intro, tries, f"Start using {plan_name}", app_url,
                   "Need help or a receipt? Write to us from the Help Center inside the app.")
    return subject, body, _text(heading, intro, tries, app_url)


def app_url() -> str:
    """The app's public address for links and pictures (Render sets RENDER_EXTERNAL_URL by itself)."""
    return (os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")


async def send(to: str, mail: tuple) -> None:
    if not mailer.configured() or not to:
        return
    try:
        await mailer.send(to, *mail)
    except Exception as exc:
        logger.warning("Email to %s failed: %s", to, exc)
