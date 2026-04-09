# Mempalace Setup

Bootstrap script + dotfiles to reproduce the full mempalace + Claude Code integration on another machine.

## What it installs

- `$HOME/.mempalace-env/` — Python venv with mempalace editable install (this fork)
- `$HOME/.mempalace/hooks/` — Stop + PreCompact hook scripts (periodic save every 10 user messages, emergency save before compaction)
- `$HOME/.claude/CLAUDE.md` — global Claude rules (PT-PT defaults, mempalace-first memory policy, verify-don't-invent)
- `$HOME/.claude/rules/mempalace.md` — lazy-loaded mempalace usage rules (AAAK format, low-token search discipline, curation policy)
- `$HOME/.claude/rules/verification.md` — state verification rules
- Merge into `$HOME/.claude/settings.json` — registers hooks, disables `autoMemoryEnabled`
- Merge into `$HOME/.claude.json` — adds mempalace as MCP server under the `$HOME` project

## Install

```bash
git clone https://github.com/jorgeccastro/mempalace.git
cd mempalace
./setup/install.sh
```

Then restart Claude Code.

## Prerequisites

- `git`, `python3` (3.12+), `jq`, `pip`
- Claude Code CLI already installed
- macOS or Linux (not tested on Windows)

## Idempotency

Safe to re-run. Existing files are backed up with suffix `.bak.YYYYMMDD-HHMMSS` before being overwritten. JSON files are deep-merged via `jq` rather than replaced.

## What's NOT included

- Your personal mempalace data (`$HOME/.mempalace/palace/`) — each user starts empty
- Personal Claude settings (status line, permission prompts, account info, skills)
- Tokens, API keys, OAuth state

## Customisation after install

The installed files are the starting point, not a permanent contract. Edit them freely:

- `~/.claude/CLAUDE.md` — change language, tone, defaults
- `~/.claude/rules/*.md` — adjust mempalace/verification rules to your workflow
- `~/.mempalace/hooks/mempal_save_hook.sh` — tune `SAVE_INTERVAL` (default: save every 10 real user messages)

## Uninstall

```bash
rm -rf $HOME/.mempalace-env $HOME/.mempalace/hooks
rm $HOME/.claude/rules/mempalace.md $HOME/.claude/rules/verification.md
# Restore CLAUDE.md, settings.json, .claude.json from their .bak files if wanted
```
