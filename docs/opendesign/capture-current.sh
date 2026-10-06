#!/usr/bin/env bash
# Capture the CURRENT ops console markup straight out of the running console.
#
# Every frame is the real rendered DOM: the console is opened in a real browser at
# http://127.0.0.1:8130, the route is set, the language is switched with the console's own
# EN/中 control, and `agent-browser get html "#ops-shell"` writes the live inner HTML to
# docs/opendesign/.capture/<screen>-<lang>.html. Nothing here re-implements the UI.
#
# Usage: bash docs/opendesign/capture-current.sh
set -u
SESSION=${SESSION:-odc}
BASE=${BASE:-http://127.0.0.1:8130}
OUT=${OUT:-docs/opendesign/.capture}
mkdir -p "$OUT"

# screen|route
SCREENS=(
  "tonight|#/tonight"
  "records|#/records"
  "records-review|#/records/review/2890514774"
  "vision|#/vision"
  "clock|#/clock"
  "regulars|#/regulars"
  "backroom|#/backroom"
)

for entry in "${SCREENS[@]}"; do
  name=${entry%%|*}
  route=${entry##*|}
  for lang in en zh; do
    agent-browser --session "$SESSION" open "$BASE/$route" >/dev/null 2>&1
    sleep 2.2
    # The console remembers the language in localStorage, so always press the wanted chip and
    # confirm the document actually switched before reading the markup. The click is dispatched
    # through the console's own button element: a pointer click can land on a screen overlay
    # (the Regulars roster panel swallows it), while .click() always reaches the handler.
    agent-browser --session "$SESSION" eval "(()=>{const b=[...document.querySelectorAll('button[data-lang=\"$lang\"]')];b.forEach(x=>x.click());return String(b.length)})()" >/dev/null 2>&1
    sleep 1.6
    # Dismiss any modal left open by a previous step. A modal is position:fixed, so in the artifact it
    # would escape its frame and cover the whole page; a capture is only written when none is open.
    open_modals=$(agent-browser --session "$SESSION" eval "(()=>{const b=document.querySelector('.modal-backdrop');if(b)b.click();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return String(document.querySelectorAll('.modal').length)})()" 2>/dev/null | tr -d '"')
    sleep 0.8
    seen=$(agent-browser --session "$SESSION" eval '(()=>document.documentElement.lang)()' 2>/dev/null | tr -d '"')
    if [ "$open_modals" != "0" ]; then
      printf '%-16s %-3s %8s             htmlLang=%-6s %s\n' "$name" "$lang" "REFUSED" "$seen" "modal still open ($open_modals)"
      continue
    fi
    agent-browser --session "$SESSION" get html "#ops-shell" > "$OUT/$name-$lang.html" 2>/dev/null
    printf '%-16s %-3s %8s bytes  htmlLang=%-6s modals=%s %s\n' "$name" "$lang" "$(wc -c < "$OUT/$name-$lang.html")" "$seen" "$open_modals" "$route"
  done
done
