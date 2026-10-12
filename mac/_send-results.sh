#!/bin/bash
# Commits whatever is in reports/ and pushes it, so Claude can read it.
# If pushing from Terminal is not set up, it tells you how to do it in
# GitHub Desktop instead — nothing is lost either way.

cd "$(dirname "$0")/.." || exit 1
MSG="${1:-Sprint results}"

git add reports/
if git diff --cached --quiet; then
  echo "Nothing new to send."
else
  if ! git commit -q -m "$MSG"; then
    echo
    echo "Could not commit (git may not know your name/email yet)."
    echo "Open GitHub Desktop → this repo → type a summary → Commit → Push origin."
    read -r -p "Press Enter to close." _; exit 1
  fi
fi

# Claude may have pushed updates meanwhile: bring them in first, or the push is refused.
git pull -q --rebase 2>/dev/null || git pull -q --no-rebase 2>/dev/null
if git push -q 2>/dev/null; then
  echo "Sent to GitHub. Tell Claude: \"results pushed\"."
else
  echo
  echo "Saved locally, but the push to GitHub did not work from Terminal."
  echo "Open GitHub Desktop → this repo → click \"Push origin\"."
  echo "Then tell Claude: \"results pushed\"."
fi
read -r -p "Press Enter to close." _
