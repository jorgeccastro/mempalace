#!/bin/bash
# MEMPALACE SAVE HOOK — periodic checkpoint every N real user messages
#
# Claude Code "Stop" hook. Fires after every assistant response.
# Every SAVE_INTERVAL external user prompts, blocks the AI and asks it to save.

SAVE_INTERVAL=10
STATE_DIR="$HOME/.mempalace/hook_state"
mkdir -p "$STATE_DIR"

INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)

# Prevent infinite loop: if we already triggered a save this cycle, allow stop
ACTIVE_FLAG="$STATE_DIR/${SESSION_ID}_active"
if [ -f "$ACTIVE_FLAG" ]; then
    rm -f "$ACTIVE_FLAG"
    echo '{"continue": true}'
    exit 0
fi

# Count only real external user prompts in transcript.
# Exclude meta/system-ish user records such as local command caveats and tool-result wrappers.
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    MSG_COUNT=$(python3 -c "
import json, sys
try:
    def is_real_user_prompt(msg):
        if msg.get('type') != 'user':
            return False
        if msg.get('isMeta') is True:
            return False
        if msg.get('userType') not in (None, 'external'):
            return False
        payload = msg.get('message', {})
        content = payload.get('content', '')
        if isinstance(content, list):
            text = ' '.join(
                part.get('text', '')
                for part in content
                if isinstance(part, dict) and part.get('type') in ('text', 'input_text', 'output_text')
            )
        else:
            text = str(content or '')
        text = text.strip()
        if not text:
            return False
        blocked_prefixes = (
            '<local-command-caveat>',
            '<local-command-stdout>',
            '<local-command-stderr>',
            '<command-name>',
        )
        if text.startswith(blocked_prefixes):
            return False
        return True

    msgs = [json.loads(l) for l in open('$TRANSCRIPT_PATH') if l.strip()]
    print(sum(1 for m in msgs if is_real_user_prompt(m)))
except:
    print(0)
" 2>/dev/null)
else
    MSG_COUNT=0
fi

# Check last save count
SAVE_FILE="$STATE_DIR/${SESSION_ID}_savecount"
LAST_SAVE=$(cat "$SAVE_FILE" 2>/dev/null || echo "0")

if [ "$((MSG_COUNT - LAST_SAVE))" -ge "$SAVE_INTERVAL" ]; then
    echo "$MSG_COUNT" > "$SAVE_FILE"
    touch "$ACTIVE_FLAG"
    echo "[$(date '+%H:%M:%S')] Save triggered at message $MSG_COUNT for session $SESSION_ID" >> "$STATE_DIR/hook.log"
    cat << 'HOOKJSON'
{
  "decision": "block",
  "reason": "PERIODIC SAVE: Save session state to mempalace. For any active task use this diary structure: TASK: <name> | STATUS: in-progress|done|blocked / DONE: <completed items> / MODIFIED: <files changed> / NEXT: <exact next step — specific enough for another agent to continue> / BLOCKED: <open decisions or blockers> / NOTES: <key decisions and why>. If no active task, save key topics, decisions, and code. Be concise but complete. Another agent may continue this work — write as if handing off to a colleague. After saving, you may stop normally."
}
HOOKJSON
else
    echo '{"continue": true}'
fi
