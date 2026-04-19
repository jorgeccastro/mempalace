# mempalace — shared VPS palace

> 🇵🇹 Português: [`VPS_SETUP.pt.md`](VPS_SETUP.pt.md)

Run a single mempalace palace on a VPS and have multiple clients
(Claude Code, Codex, etc. across different machines) talk to it via SSH.

This is an **optional** alternative to the default standalone install
(`setup/install.sh`) where every client has its own palace.

## Architecture

```
┌───────────────┐    SSH (stdio)    ┌──────────────────┐
│ client PC #1  │ ────────────────▶ │ VPS              │
│ Claude Code   │                   │ mempalace.mcp_sv │
└───────────────┘                   │ palace (single)  │
                                    │ KG (single)      │
┌───────────────┐    SSH (stdio)    │                  │
│ client PC #2  │ ────────────────▶ │                  │
│ Codex         │                   │                  │
└───────────────┘                   └──────────────────┘
┌───────────────┐    SSH (stdio)
│ client PC #3  │ ───────────────────────────▶
│ Claude Code   │
└───────────────┘
```

- **Palace + KG live on the VPS** — single source of truth across all clients.
- **Transport is SSH stdio** — no open ports, works through any firewall
  that lets SSH out. Use Tailscale / WireGuard / Cloudflare Tunnel if you
  want mesh networking; plain public SSH works too.
- **Clients run no mempalace process** — the MCP server executes on the VPS
  when Claude Code spawns the `ssh …` command. Kill SSH, kill the server.

## Prerequisites

- A VPS (any Linux) with SSH access and Python 3.11+.
- A dedicated unprivileged user on the VPS (e.g., `mempalace`). Don't run
  mempalace as root.
- On every client PC: an SSH key you are willing to add to the VPS user's
  `authorized_keys`.
- (Optional, recommended) Tailscale or equivalent so the VPS is reachable
  without exposing SSH to the public internet.

## 1 — Server install (VPS)

SSH into the VPS, create the service user if it doesn't exist, and run the
server installer inside a clone of your fork:

```bash
ssh you@your-vps
sudo useradd -m -s /bin/bash mempalace      # skip if user exists
sudo -iu mempalace
git clone <your-fork-url> ~/mempalace-source
cd ~/mempalace-source
./setup/install-vps-server.sh
```

What it does:
- installs `uv` if missing
- creates `~/.mempalace-env` venv
- `uv pip install -e .` from the clone
- creates `~/.mempalace/` data dir
- prints the command clients will use

What it does NOT do:
- add SSH keys (you do that by appending client pubkeys to
  `/home/mempalace/.ssh/authorized_keys`)
- install Tailscale / configure firewall / manage DNS
- set up a systemd service — the MCP server is spawned on-demand per
  client SSH session, which is simpler and doesn't need supervision

## 2 — Authorize client SSH keys

On each client, generate a key if you don't have one:

```bash
ssh-keygen -t ed25519 -C "your-client-hostname"
cat ~/.ssh/id_ed25519.pub
```

Copy the pubkey line and on the VPS, as the mempalace user:

```bash
echo "ssh-ed25519 AAAA…" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Test from the client:

```bash
ssh mempalace@your-vps-host "whoami"   # should print: mempalace
```

## 3 — Client install (per client PC)

Clone the repo (any dir — it's only used for the installer script) and run:

```bash
git clone <your-fork-url> ~/src/mempalace-source
cd ~/src/mempalace-source
VPS_HOST=your-vps-host ./setup/install-vps-client.sh
```

It prompts for (or reads from env):
- `VPS_HOST` — Tailscale name, DNS name, or IP
- `VPS_USER` — SSH user (default `mempalace`)
- `VPS_PYTHON` — path to the VPS venv python (default
  `/home/mempalace/.mempalace-env/bin/python`)

It then either patches `~/.claude.json` (`mcpServers.mempalace`) or prints
the resolved entry for you to paste manually.

Restart Claude Code after patching; the MCP server should show up as
`mempalace` with `mempalace_search`, `mempalace_kg_*`, `mempalace_diary_*`,
etc.

## Optional — install the CLI locally too

The MCP server runs entirely on the VPS, so the client-side CLI is only
needed if you want local `mempalace mine` / `codex_checkpoint_watcher`:

```bash
./setup/install.sh       # standard local install, no VPS needed for CLI
```

The local CLI can share the palace path via SSHFS/NFS or just point at a
local working palace — it's independent of the VPS MCP flow.

## Troubleshooting

- **`Permission denied (publickey)`** — your client pubkey isn't in the
  VPS user's `authorized_keys`. Re-check step 2.
- **MCP server shows "connecting" forever** — test the raw command:
  `ssh mempalace@vps /home/mempalace/.mempalace-env/bin/python -m mempalace.mcp_server`.
  If it hangs silently, that's correct (it's waiting for JSON-RPC on stdin).
  Send `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}` to
  verify.
- **`ModuleNotFoundError: mempalace`** on VPS — venv broken; re-run
  `./setup/install-vps-server.sh`.
- **Stale HNSW index after CLI writes** — call `mempalace_reconnect` from
  the client to force the MCP server to reopen collections.
