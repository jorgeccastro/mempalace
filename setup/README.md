# Mempalace Setup

Bootstrap scripts + dotfiles to reproduce the full mempalace + Claude Code
integration on another machine.

## Two install modes

Pick one — they're mutually complementary, not exclusive.

| Mode | Palace lives on | Good for |
|---|---|---|
| **A. Standalone local** (`./install.sh`) | Each machine | Single-PC users, offline work, full CLI features (`mine`, `codex_checkpoint_watcher`) |
| **B. Shared VPS palace** (`./install-vps-server.sh` + `./install-vps-client.sh`) | One VPS, shared across N clients via SSH | Multi-machine setups, cross-device memory continuity, team-style shared memory |

You can also run **both**: local CLI + remote MCP. The CLI uses a local palace; Claude Code uses the VPS palace. They don't interfere.

---

## A. Standalone local install

### What it installs

- `$HOME/.mempalace-env/` — Python venv with mempalace editable install (this fork)
- `$HOME/.mempalace/hooks/` — Stop + PreCompact hook scripts (periodic save every 10 user messages, emergency save before compaction)
- `$HOME/.claude/CLAUDE.md` — global Claude rules (PT-PT defaults, mempalace-first memory policy, verify-don't-invent)
- `$HOME/.claude/rules/mempalace.md` — lazy-loaded mempalace usage rules (AAAK format, low-token search discipline, curation policy)
- `$HOME/.claude/rules/verification.md` — state verification rules
- Merge into `$HOME/.claude/settings.json` — registers hooks, disables `autoMemoryEnabled`
- Merge into `$HOME/.claude.json` — adds mempalace as MCP server under the `$HOME` project

### Install

```bash
git clone <your-fork-url> mempalace
cd mempalace
./setup/install.sh
```

Then restart Claude Code.

### Prerequisites

- `git`, `python3` (3.12+), `jq`, `pip`
- Claude Code CLI already installed
- macOS or Linux (not tested on Windows)

### Idempotency

Safe to re-run. Existing files are backed up with suffix `.bak.YYYYMMDD-HHMMSS` before being overwritten. JSON files are deep-merged via `jq` rather than replaced.

---

## B. Shared VPS palace

Run a single mempalace palace on a VPS, connect multiple clients to it via SSH stdio. See **[`VPS_SETUP.md`](VPS_SETUP.md)** for architecture, prerequisites, and full walkthrough.

Quick flow:

```bash
# ── On the VPS (as a dedicated unprivileged user) ──────────────────────
git clone <your-fork-url> ~/mempalace-source
cd ~/mempalace-source
./setup/install-vps-server.sh
# then add client SSH pubkeys to ~/.ssh/authorized_keys

# ── On each client ─────────────────────────────────────────────────────
git clone <your-fork-url> ~/src/mempalace-source
cd ~/src/mempalace-source
VPS_HOST=your-vps-host ./setup/install-vps-client.sh
```

The client installer prompts (or accepts env vars) for `VPS_HOST`, `VPS_USER` (default `mempalace`), and `VPS_PYTHON` (default `/home/mempalace/.mempalace-env/bin/python`), then either auto-patches `~/.claude.json` or prints the ready-to-paste MCP entry.

Transport is SSH stdio — no open ports, works through any firewall that permits outbound SSH. Use Tailscale / WireGuard / Cloudflare Tunnel if you want private mesh networking; plain public SSH works too.

---

## What's NOT included (either mode)

- Your personal mempalace data (`$HOME/.mempalace/palace/`) — each install starts empty
- Personal Claude settings (status line, permission prompts, account info, skills)
- Tokens, API keys, OAuth state
- SSH keys, Tailscale configs, firewall rules (VPS mode operator's responsibility)

## Customisation after install

The installed files are the starting point, not a permanent contract. Edit them freely:

- `~/.claude/CLAUDE.md` — change language, tone, defaults
- `~/.claude/rules/*.md` — adjust mempalace/verification rules to your workflow
- `~/.mempalace/hooks/mempal_save_hook.sh` — tune `SAVE_INTERVAL` (default: save every 10 real user messages)

## Uninstall

**Standalone:**
```bash
rm -rf $HOME/.mempalace-env $HOME/.mempalace/hooks
rm $HOME/.claude/rules/mempalace.md $HOME/.claude/rules/verification.md
# Restore CLAUDE.md, settings.json, .claude.json from their .bak files if wanted
```

**VPS client:**
```bash
# Remove the mcpServers.mempalace entry from ~/.claude.json
# Revoke the client's pubkey from the VPS user's authorized_keys
```

**VPS server:**
```bash
# On the VPS, as the mempalace user
rm -rf ~/.mempalace-env ~/.mempalace ~/mempalace-source
# Then remove the user if dedicated: sudo userdel -r mempalace
```
