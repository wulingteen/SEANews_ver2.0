#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: scripts/task_commit.sh <TASK_ID> <summary>"
  echo "Example: scripts/task_commit.sh VC-01 \"remove forced relogin\""
  exit 1
fi

TASK_ID="$1"
shift
SUMMARY="$*"

if git diff --cached --quiet; then
  echo "No staged changes found."
  echo "Stage files first, then run this command again."
  exit 1
fi

echo "Committing staged changes with task ID ${TASK_ID}..."
git commit -m "task(${TASK_ID}): ${SUMMARY}"
echo "Done."
echo "Reminder: update VIBE_TASKS.md and vibe_tasks.json for next task."

