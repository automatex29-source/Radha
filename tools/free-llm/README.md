# Free LLM fallback for Claude Code

Use this when your Claude limit is close or used up. It runs Claude Code on
free models (Google, Groq, Cerebras, OpenRouter and others) through
[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi), a free tool that
runs on your own computer.

Your normal `claude` command is **not changed**. You only get free models when
you start Claude Code with the script below. Close it and run `claude` again to
go back to real Claude.

## One-time setup (about 10 minutes, on your computer)

1. **Install FreeLLMAPI.** Download the desktop app from
   <https://github.com/tashfeenahmed/freellmapi/releases/latest>
   (Windows: `.exe`. Mac: `arm64` for M1 to M4, `x64` for Intel).
   You also need Node.js 20 or newer (<https://nodejs.org>).
2. **Add free provider keys.** Open the app (tray icon), make free accounts at a
   few providers (Google AI Studio, Groq, Cerebras, Mistral, OpenRouter), create
   an API key at each and paste them on the **Keys** page. More keys means more
   free capacity.
3. **Copy your unified key.** Tray icon, then **Copy Key**. It starts with
   `freellmapi-`.
4. **Save it for these scripts** (pick one):
   - Put it in a file named `.key` in this folder (`tools/free-llm/.key`).
     That file is git-ignored, so it never goes to GitHub.
   - Or set the environment variable `FREELLMAPI_API_KEY`.

## Every day

From the repo folder:

| Computer | Command |
| --- | --- |
| Windows (PowerShell) | `.\tools\free-llm\free-claude.ps1` |
| Mac / Linux | `./tools/free-llm/free-claude.sh` |

Anything you type after the command is passed to Claude Code, for example
`./tools/free-llm/free-claude.sh --continue`.

The script checks that FreeLLMAPI is running, then starts Claude Code with the
free gateway. Nothing is written to your Claude settings, so quitting returns
you to normal.

## Good to know

- **It only works on your own computer.** Claude Code sessions in the cloud
  (claude.ai/code) cannot reach the FreeLLMAPI app on your PC, so they keep
  using your Claude plan.
- Free models are weaker than Claude. Use them for simple edits, questions and
  small fixes, and save Claude for hard work.
- Each provider has its own free limits and terms. This is for your own
  personal coding, not for Krish's users.
- Keep the key private and do not open FreeLLMAPI to the internet: anyone with
  the key can use your free quota.
- The script finds the app on its own: the desktop app uses port 31415 and the
  Docker install uses 3001. Set `FREELLMAPI_URL` to use another address.
- Something wrong? Run `npx freellmapi doctor`.
