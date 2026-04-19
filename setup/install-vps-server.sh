#!/usr/bin/env bash
#
# mempalace VPS server installer
#
# Run this ON THE VPS as the unprivileged user that will own the palace
# (typically a dedicated account like `mempalace`). It creates a Python
# venv, installs mempalace editable from the current clone, and writes the
# palace dir layout. It does NOT manage SSH keys, firewall, or Tailscale —
# those stay with the operator.
#
# Assumes:
#   * Current user is NOT root.
#   * This clone of the mempalace fork is the one you want to run.
#   * uv is installed (or installable via pipx/curl).
#
# Usage:
#   ssh you@your-vps
#   sudo useradd -m -s /bin/bash mempalace     # one-time, if you don't have the user yet
#   sudo -iu mempalace
#   git clone <your fork url> ~/mempalace-source
#   cd ~/mempalace-source
#   ./setup/install-vps-server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV="$HOME/.mempalace-env"
MEMPAL_DIR="$HOME/.mempalace"
PALACE_DIR="$MEMPAL_DIR/palace"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }
die()    { red "ERROR: $*"; exit 1; }

[[ "$EUID" -ne 0 ]] || die "Do not run as root. sudo -iu <mempalace-user> first."
[[ -f "$REPO_ROOT/pyproject.toml" ]] || die "Not a mempalace clone (no pyproject.toml at $REPO_ROOT)"

blue "Installing mempalace server for user: $(whoami)"
blue "  Repo : $REPO_ROOT"
blue "  Venv : $VENV"
blue "  Data : $MEMPAL_DIR"

# --- uv -----------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    yellow "uv not found. Installing to ~/.local/bin ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv install failed. Install manually: https://docs.astral.sh/uv/"
fi

# --- venv ---------------------------------------------------------------
if [[ ! -d "$VENV" ]]; then
    blue "Creating venv at $VENV ..."
    uv venv "$VENV"
fi

# --- install mempalace editable -----------------------------------------
blue "Installing mempalace editable ..."
uv pip install -e "$REPO_ROOT" --python "$VENV/bin/python"

# --- data dirs ----------------------------------------------------------
mkdir -p "$MEMPAL_DIR"
mkdir -p "$MEMPAL_DIR/hooks"

# --- verify -------------------------------------------------------------
blue "Verifying install ..."
VER=$("$VENV/bin/python" -c 'import mempalace; print(mempalace.__version__)')
green "  mempalace $VER imported OK"

# --- sanity-check MCP server starts -------------------------------------
blue "Booting MCP server (3s timeout) ..."
timeout 3 "$VENV/bin/python" -m mempalace.mcp_server </dev/null 2>&1 | head -5 || true

cat <<EOF

$(green "Server install complete.")

Palace path : $PALACE_DIR (created on first mine/write)
Venv python : $VENV/bin/python
MCP command : $VENV/bin/python -m mempalace.mcp_server

NEXT — for each client PC that should connect:

  1. Make sure the client can reach this VPS (Tailscale, WireGuard, or direct SSH).
  2. On the client, add its SSH pubkey to THIS account's authorized_keys:
       cat ~/.ssh/id_ed25519.pub            # on the client
       >> $HOME/.ssh/authorized_keys        # on the VPS
  3. On the client, run:
       ./setup/install-vps-client.sh
     with VPS_HOST=<this-host>, VPS_USER=$(whoami), VPS_PYTHON=$VENV/bin/python

EOF
