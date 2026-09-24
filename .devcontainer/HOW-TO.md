# RADHA is starting 🚀

The first start builds everything and takes **about 10 minutes**. Later starts take under a minute.

- **When it's ready**, RADHA opens in a new browser tab. If it doesn't, open the **Ports** tab
  at the bottom of this window and click the globe icon next to **RADHA (8080)**.
- **Create your account** with Register — this copy of RADHA is yours alone.
- **Watch progress**: in the Terminal below, run `docker compose logs -f radha`
  and wait for `Application startup complete`.

## API keys
If you entered keys when creating the Codespace, you're done. To add or change keys later,
either:
- add them at https://github.com/settings/codespaces (Codespaces secrets, give this repository
  access), then rebuild; **or**
- create a file named `.env` here (copy `.env.example`), paste your keys, and run
  `docker compose up -d` in the Terminal.

## Stopping
Codespaces stop automatically after 30 minutes of inactivity (this saves your free hours).
Your chats and apps are kept. Delete the Codespace at https://github.com/codespaces when
you no longer need it.
