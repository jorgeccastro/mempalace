#!/bin/bash
# MEMPALACE SAVE HOOK — hybrid checkpoint: messages + time
#
# Claude Code "Stop" hook. Fires after every assistant response.
# Only triggers a save when BOTH conditions are met since the last save:
#   - At least SAVE_MSG_INTERVAL real user messages
#   - At least SAVE_TIME_INTERVAL seconds have passed

SAVE_MSG_INTERVAL=15
SAVE_TIME_INTERVAL=1800  # 30 minutes

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

# Count only real external user prompts in transcript
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

NOW=$(date +%s)

# Read last save state (message count and timestamp)
SAVE_FILE="$STATE_DIR/${SESSION_ID}_savecount"
TIME_FILE="$STATE_DIR/${SESSION_ID}_savetime"
LAST_SAVE_MSG=$(cat "$SAVE_FILE" 2>/dev/null || echo "0")
LAST_SAVE_TIME=$(cat "$TIME_FILE" 2>/dev/null || echo "0")

# Initialize time on first run
if [ "$LAST_SAVE_TIME" = "0" ]; then
    echo "$NOW" > "$TIME_FILE"
    LAST_SAVE_TIME=$NOW
fi

MSG_DIFF=$((MSG_COUNT - LAST_SAVE_MSG))
TIME_DIFF=$((NOW - LAST_SAVE_TIME))

if [ "$MSG_DIFF" -ge "$SAVE_MSG_INTERVAL" ] && [ "$TIME_DIFF" -ge "$SAVE_TIME_INTERVAL" ]; then
    echo "$MSG_COUNT" > "$SAVE_FILE"
    echo "$NOW" > "$TIME_FILE"
    touch "$ACTIVE_FLAG"
    echo "[$(date '+%H:%M:%S')] Save triggered at message $MSG_COUNT (${TIME_DIFF}s elapsed) for session $SESSION_ID" >> "$STATE_DIR/hook.log"
    cat << 'HOOKJSON'
{
  "decision": "block",
  "reason": "PERIODIC SAVE: Save session state to mempalace diary. Use AAAK format: SESSION:<date>|TOPIC:<name>|STATUS:<done|in-progress|blocked> / CTX:<pedido do user> / FIND:<descobertas> / ACT:<acções numeradas> / MODIFIED:<ficheiros+detalhe> / DEC:<decisões duradouras> / USR-FEEDBACK:<reacção do user> / LESSON:<aprendizagens> / NEXT:<próximo passo para handoff> / ★. Obrigatórios: SESSION,TOPIC,STATUS,ACT,★. Restantes só se aplicável. Be concise. Another agent may continue — write as handoff."
}
HOOKJSON
else
    echo '{"continue": true}'
fi
