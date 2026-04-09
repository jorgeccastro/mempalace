#!/usr/bin/env bash
#
# mempalace bootstrap installer
#
# Installs the mempalace fork (editable) + Claude Code integration dotfiles
# onto this machine. Idempotent: backs up any pre-existing files before
# overwriting.
#
# Run from a clone of the fork:
#   git clone https://github.com/jorgeccastro/mempalace.git
#   cd mempalace
#   ./setup/install.sh
#

set -euo pipefail

# --- Paths ---------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOTFILES="$SCRIPT_DIR/dotfiles"
SNIPPETS="$SCRIPT_DIR/snippets"

VENV="$HOME/.mempalace-env"
CLAUDE_DIR="$HOME/.claude"
CLAUDE_JSON="$HOME/.claude.json"
MEMPAL_DIR="$HOME/.mempalace"
HOOKS_DIR="$MEMPAL_DIR/hooks"

STAMP=$(date +%Y%m%d-%H%M%S)

# --- Helpers -------------------------------------------------------------

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

die() { red "ERROR: $*"; exit 1; }

backup() {
    local f="$1"
    if [ -e "$f" ] || [ -L "$f" ]; then
        cp -a "$f" "${f}.bak.${STAMP}"
        echo "  backup: $f → ${f}.bak.${STAMP}"
    fi
}

# Replace __HOME__ placeholder with actual $HOME
substitute() {
    sed "s|__HOME__|$HOME|g" "$1"
}

# --- Sanity checks -------------------------------------------------------

blue "==> Sanity checks"

[ -f "$REPO_ROOT/pyproject.toml" ] || die "no pyproject.toml at $REPO_ROOT — run install.sh from inside a mempalace clone"
grep -q 'name = "mempalace"' "$REPO_ROOT/pyproject.toml" || die "$REPO_ROOT is not a mempalace repo"

for cmd in git python3 jq pip; do
    command -v "$cmd" >/dev/null || die "$cmd not found in PATH"
done

green "  ok"

# --- 1. Python venv ------------------------------------------------------

blue "==> [1/6] Python venv at $VENV"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    green "  created"
else
    green "  exists"
fi

# --- 2. Install mempalace (editable) -------------------------------------

blue "==> [2/6] pip install -e $REPO_ROOT"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$REPO_ROOT"
green "  installed"

# --- 3. Hooks ------------------------------------------------------------

blue "==> [3/6] Hooks → $HOOKS_DIR"
mkdir -p "$HOOKS_DIR"
for hook in "$DOTFILES/hooks/"*.sh; do
    dest="$HOOKS_DIR/$(basename "$hook")"
    backup "$dest"
    install -m 755 "$hook" "$dest"
    echo "  installed: $(basename "$hook")"
done

# --- 4. Claude rules + CLAUDE.md -----------------------------------------

blue "==> [4/6] Claude rules → $CLAUDE_DIR"
mkdir -p "$CLAUDE_DIR/rules"

backup "$CLAUDE_DIR/CLAUDE.md"
substitute "$DOTFILES/CLAUDE.md" > "$CLAUDE_DIR/CLAUDE.md"
echo "  installed: CLAUDE.md"

for rule in "$DOTFILES/rules/"*.md; do
    dest="$CLAUDE_DIR/rules/$(basename "$rule")"
    backup "$dest"
    substitute "$rule" > "$dest"
    echo "  installed: rules/$(basename "$rule")"
done

# --- 5. Merge settings.json ---------------------------------------------

SETTINGS="$CLAUDE_DIR/settings.json"
blue "==> [5/6] Merge settings fragment → $SETTINGS"
backup "$SETTINGS"

if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

FRAGMENT=$(substitute "$SNIPPETS/settings-fragment.json")
jq --argjson frag "$FRAGMENT" '. * $frag' "$SETTINGS" > "$SETTINGS.tmp"
mv "$SETTINGS.tmp" "$SETTINGS"
green "  merged (deep merge via jq — note: existing hook arrays are replaced, not appended)"

# --- 6. Merge MCP entry into .claude.json -------------------------------

blue "==> [6/6] Merge MCP entry → $CLAUDE_JSON"
backup "$CLAUDE_JSON"

if [ ! -f "$CLAUDE_JSON" ]; then
    echo '{}' > "$CLAUDE_JSON"
fi

MCP_ENTRY=$(substitute "$SNIPPETS/mcp-entry.json")
jq --arg home "$HOME" --argjson mcp "$MCP_ENTRY" '
    .projects //= {} |
    .projects[$home] //= {} |
    .projects[$home].mcpServers //= {} |
    .projects[$home].mcpServers.mempalace = $mcp
' "$CLAUDE_JSON" > "$CLAUDE_JSON.tmp"
mv "$CLAUDE_JSON.tmp" "$CLAUDE_JSON"
green "  merged (mempalace added under projects[\"$HOME\"].mcpServers)"

# --- Done ----------------------------------------------------------------

echo ""
green "============================================================"
green "  Done. Restart Claude Code to activate the mempalace MCP."
green "============================================================"
echo ""
echo "Installed:"
echo "  - venv:     $VENV"
echo "  - hooks:    $HOOKS_DIR"
echo "  - rules:    $CLAUDE_DIR/rules/"
echo "  - settings: $SETTINGS (merged)"
echo "  - MCP:      $CLAUDE_JSON (merged)"
echo ""
echo "Backups of pre-existing files have suffix .bak.$STAMP"
echo ""
yellow "Next steps:"
echo "  1. Restart Claude Code"
echo "  2. Verify MCP with /mcp — you should see 'mempalace' listed"
echo "  3. Try: 'what's in my diary?' — should call mempalace_diary_read"
