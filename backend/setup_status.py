"""Owner only: which connectors and plugins are live on this server, and the exact keys the rest still need.

Each item lists the Render environment variables it needs and plain steps to get them. Only whether a key
is set is reported, never its value.
"""
import os

SITE = "https://krishai.net"


def _set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _site() -> str:
    for k in ("PUBLIC_URL", "APP_URL", "RENDER_EXTERNAL_URL"):
        if _set(k):
            return os.environ[k].strip().rstrip("/")
    return SITE


def items() -> list:
    site = _site()
    return [
        {"id": "telegram", "name": "Telegram", "effort": "5 minutes", "keys": ["TELEGRAM_BOT_TOKEN"],
         "unlocks": "Users chat with Krish on Telegram and get automation results there",
         "link": "https://t.me/BotFather",
         "steps": ["In Telegram, open @BotFather and send /newbot",
                   "Pick a name (like Krish AI) and a username ending in bot (like KrishAIBot)",
                   "Copy the token it sends (looks like 123456:ABC-...)",
                   "In Render > your service > Environment, add TELEGRAM_BOT_TOKEN with that token and save",
                   "Done: Krish sets up the bot's webhook on its own the first time someone connects"]},
        {"id": "google", "name": "Google Drive, Sheets, Calendar and Gmail", "effort": "20 minutes, then Google review",
         "keys": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
         "unlocks": "Users connect their Google account to read files, add rows, see their calendar and draft emails",
         "link": "https://console.cloud.google.com/apis/credentials",
         "steps": ["Open Google Cloud > APIs & Services > Credentials and open the OAuth client you use for Google sign-in",
                   f"Under Authorized redirect URIs add {site}/api/connectors/oauth/callback and save",
                   "Copy the Client secret and add it in Render as GOOGLE_CLIENT_SECRET",
                   "In APIs & Services > Library, enable Google Drive API, Google Sheets API, Google Calendar API and Gmail API",
                   "In OAuth consent screen > Data access, add the Drive (read-only), Sheets, Calendar events and Gmail scopes",
                   "Until Google verifies the app, add up to 100 test users under Audience; for everyone, press Publish and submit for verification (Gmail needs a security review)"]},
        {"id": "whatsapp", "name": "WhatsApp (chat with Krish)", "effort": "30 minutes, then Meta review",
         "keys": ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_NUMBER", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"],
         "unlocks": "Users message Krish on WhatsApp and get automation results there",
         "link": "https://developers.facebook.com/apps",
         "steps": ["Create a Business app at developers.facebook.com and add the WhatsApp product",
                   "In WhatsApp > API Setup, add Krish's phone number and copy its Phone number ID (WHATSAPP_PHONE_ID); WHATSAPP_NUMBER is the number itself, like 919876543210",
                   "In Business Settings > System users, make a system user, give it the app, and create a permanent token with whatsapp_business_messaging (WHATSAPP_TOKEN)",
                   "In App settings > Basic copy the App secret (WHATSAPP_APP_SECRET)",
                   f"In WhatsApp > Configuration set the webhook to {site}/api/connectors/whatsapp/webhook with any password you choose as the verify token (WHATSAPP_VERIFY_TOKEN), and subscribe to messages",
                   "Add all five in Render and save"]},
        {"id": "video", "name": "Video maker", "effort": "2 minutes (paid per second of video)",
         "keys": ["VIDEO_GENERATION"], "any": ["OPENAI_API_KEY", "FAL_KEY", "POLLINATIONS_API_KEY"],
         "unlocks": "Pro and Max users make short videos and reels",
         "link": "https://dashboard.render.com",
         "steps": ["In Render, add VIDEO_GENERATION with the value on",
                   "It needs one video service key: OPENAI_API_KEY (Sora), FAL_KEY (Veo) or POLLINATIONS_API_KEY",
                   "Each second of video costs money on that service, so check its prices first"]},
        {"id": "github", "name": "GitHub one-click sign-in (optional)", "effort": "5 minutes",
         "keys": ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"],
         "unlocks": "Already live with a pasted token; this adds a one-click Connect button",
         "link": "https://github.com/settings/applications/new",
         "steps": [f"Create a GitHub OAuth app with callback {site}/api/connectors/oauth/callback",
                   "Copy its Client ID and make a Client secret, then add both in Render"]},
        {"id": "notion", "name": "Notion one-click sign-in (optional)", "effort": "5 minutes",
         "keys": ["NOTION_CLIENT_ID", "NOTION_CLIENT_SECRET"],
         "unlocks": "Already live with a pasted secret; this adds a one-click Connect button",
         "link": "https://www.notion.so/profile/integrations",
         "steps": [f"Create a public Notion integration with redirect {site}/api/connectors/oauth/callback",
                   "Copy its OAuth client ID and secret, then add both in Render"]},
    ]


def status() -> dict:
    out = []
    for it in items():
        missing = [k for k in it["keys"] if not _set(k)]
        if it["id"] == "video" and not missing and os.environ.get("VIDEO_GENERATION", "").strip().lower() not in (
                "1", "on", "true", "yes"):
            missing = ["VIDEO_GENERATION"]
        if it.get("any") and not any(_set(k) for k in it["any"]):
            missing.append(" or ".join(it["any"]))
        out.append({**{k: v for k, v in it.items() if k != "any"}, "live": not missing, "missing": missing})
    always = ["Slack", "Discord", "GitHub (pasted token)", "Notion (pasted secret)", "Add any app (MCP and webhooks)",
              "Weather", "Panchang & festivals", "Cricket scores", "Always search the web", "Daily Gita verse"]
    return {"items": out, "alwaysLive": always, "live": sum(i["live"] for i in out), "total": len(out)}
