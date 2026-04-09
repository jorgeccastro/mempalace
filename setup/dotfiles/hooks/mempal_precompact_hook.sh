#!/bin/bash
# MEMPALACE PRE-COMPACT HOOK — Emergency save before compaction
#
# Claude Code "PreCompact" hook. Fires RIGHT BEFORE the conversation
# gets compressed to free up context window space.

STATE_DIR="$HOME/.mempalace/hook_state"
mkdir -p "$STATE_DIR"

# Optional: set to the directory you want auto-ingested before compaction.
MEMPAL_DIR=""

INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)

echo "[$(date '+%H:%M:%S')] PRE-COMPACT triggered for session $SESSION_ID" >> "$STATE_DIR/hook.log"

if [ -n "$MEMPAL_DIR" ] && [ -d "$MEMPAL_DIR" ]; then
    ~/.mempalace-env/bin/mempalace mine "$MEMPAL_DIR" >> "$STATE_DIR/hook.log" 2>&1
fi

cat << 'HOOKJSON'
{
  "decision": "block",
  "reason": "COMPACTION IMMINENT. Save ALL context from this session to mempalace. For any active task use this diary structure: TASK: <name> | STATUS: in-progress|done|blocked / DONE: <completed items> / MODIFIED: <files changed> / NEXT: <exact next step — specific enough for another agent to continue> / BLOCKED: <open decisions or blockers> / NOTES: <key decisions and why>. Also save all other topics, decisions, quotes, and code. Be thorough — after compaction, detailed context will be lost. Another agent (Claude or Codex) may continue this work — write as if handing off to a colleague. Save everything, then allow compaction to proceed."
}
HOOKJSON
