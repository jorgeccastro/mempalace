#!/usr/bin/env bash
#
# mempalace VPS client installer
#
# Registers a remote mempalace MCP server — running on your own VPS — in
# this machine's Claude Code config (~/.claude.json). The client speaks to
# the VPS over SSH (stdio transport), so no ports are opened publicly.
#
# What this DOES:
#   * Prompts for VPS_HOST, VPS_USER, VPS_PYTHON (or reads env vars)
#   * Tests SSH reachability (BatchMode — no password prompt)
#   * Writes a ready-to-paste MCP entry to stdout
#   * Optionally patches ~/.claude.json (with timestamped backup)
#
# What this does NOT do:
#   * Install mempalace on the VPS (run setup/install-vps-server.sh there)
#   * Configure your network (Tailscale / VPN / plain internet — your call)
#   * Authorize your SSH key on the VPS (add the pubkey to VPS authorized_keys yourself)
#
# Usage:
#   VPS_HOST=myvps.tailnet ./setup/install-vps-client.sh
#   # or run interactively:
#   ./setup/install-vps-client.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/snippets/mcp-entry-vps.template.json"
[[ -f "$TEMPLATE" ]] || { echo "ERROR: template not found at $TEMPLATE" >&2; exit 1; }

CLAUDE_JSON="${CLAUDE_JSON:-$HOME/.claude.json}"

: "${VPS_HOST:=}"
: "${VPS_USER:=mempalace}"
: "${VPS_PYTHON:=/home/mempalace/.mempalace-env/bin/python}"
: "${SERVER_NAME:=mempalace}"
: "${SCOPE:=user}"    # user = top-level mcpServers; project = projects.<cwd>.mcpServers

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

prompt_if_empty() {
    local var="$1" msg="$2" def="${3:-}"
    local cur="${!var}"
    if [[ -z "$cur" ]]; then
        local val
        if [[ -n "$def" ]]; then
            read -rp "$msg [$def]: " val
            val="${val:-$def}"
        else
            read -rp "$msg: " val
        fi
        printf -v "$var" '%s' "$val"
    fi
}

blue "mempalace VPS client installer"

prompt_if_empty VPS_HOST  "VPS host (Tailscale name, DNS, or IP)"
prompt_if_empty VPS_USER  "VPS SSH user" "mempalace"
prompt_if_empty VPS_PYTHON "VPS python path (mempalace venv)" "/home/mempalace/.mempalace-env/bin/python"

[[ -z "$VPS_HOST" ]] && { red "ERROR: VPS_HOST required"; exit 1; }

blue "Testing SSH reachability to $VPS_USER@$VPS_HOST ..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 "$VPS_USER@$VPS_HOST" "true" 2>/dev/null; then
    green "  OK."
else
    yellow "  WARNING: SSH test failed (BatchMode)."
    yellow "  Check: (1) network reachable, (2) your SSH pubkey present in VPS ~/.ssh/authorized_keys"
    read -rp "Continue anyway? [y/N]: " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

ENTRY_JSON=$(sed \
    -e "s|__VPS_HOST__|$VPS_HOST|g" \
    -e "s|__VPS_USER__|$VPS_USER|g" \
    -e "s|__VPS_PYTHON__|$VPS_PYTHON|g" \
    "$TEMPLATE")

echo
blue "Resolved MCP entry (name: $SERVER_NAME):"
echo "$ENTRY_JSON"
echo

read -rp "Patch $CLAUDE_JSON automatically? [y/N]: " yn
if [[ ! "$yn" =~ ^[Yy]$ ]]; then
    yellow "Skipped auto-patch. Paste the entry above into your Claude Code config manually."
    exit 0
fi

if [[ -f "$CLAUDE_JSON" ]]; then
    BACKUP="$CLAUDE_JSON.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$CLAUDE_JSON" "$BACKUP"
    green "Backup saved: $BACKUP"
fi

python3 - "$CLAUDE_JSON" "$SERVER_NAME" "$SCOPE" <<PYEOF
import json, os, sys
path, name, scope = sys.argv[1], sys.argv[2], sys.argv[3]
entry = json.loads('''$ENTRY_JSON''')

data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"ERROR: could not parse {path}: {e}", file=sys.stderr)
        sys.exit(1)

if scope == "project":
    key = os.path.abspath(os.getcwd())
    projects = data.setdefault("projects", {})
    proj = projects.setdefault(key, {})
    mcps = proj.setdefault("mcpServers", {})
    loc = f"projects.{key}.mcpServers.{name}"
else:
    mcps = data.setdefault("mcpServers", {})
    loc = f"mcpServers.{name}"

mcps[name] = entry
json.dump(data, open(path, "w"), indent=2)
print(f"Wrote {loc}")
PYEOF

green "Done. Restart Claude Code to pick up the new MCP server."
