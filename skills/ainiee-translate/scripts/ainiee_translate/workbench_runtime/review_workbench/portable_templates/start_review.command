#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required. See OPEN-ME.txt."
  read -r -p "Press Enter to close. "
  exit 1
fi
python3 start_review.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
  read -r -p "Read the message above and OPEN-ME.txt. Press Enter to close. "
fi
exit "$status"
