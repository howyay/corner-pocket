#!/usr/bin/env bash
# One entry point for the four test suites of this repository.
#
#   pool-test.sh          all four suites
#   pool-test.sh python   the python suite
#   pool-test.sh js       the three javascript suites
#
# A bare `node --test` is not a test command here: no file name matches the node default
# patterns (*.test.js, test-*.js), so it collects 0 tests and exits 0 (measured, node v24.21.0).
# Each javascript suite carries its own runner, so name it.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"

run_python() {
  echo "== python: unittest discover -s tests"
  PYTHONPATH=. "$PYTHON" -m unittest discover -s tests -p 'test_*.py'
}

run_js() {
  for suite in tests/test_ops.js tests/test_board.js tests/test_app_timeline.js; do
    echo "== node: $suite"
    node "$suite"
  done
}

case "${1:-all}" in
  all)    run_python; run_js ;;
  python) run_python ;;
  js)     run_js ;;
  *)      echo "usage: $0 [all|python|js]" >&2; exit 2 ;;
esac
