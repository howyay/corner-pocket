#!/usr/bin/env bash
# One entry point for the four test suites of this repository.
#
#   pool-test.sh                  all four suites
#   pool-test.sh python           the python suite
#   pool-test.sh python <module>  one python module, by the bare name of its file
#   pool-test.sh js               the three javascript suites
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

# One module, named by its file without the .py suffix.
#
# The dotted spelling `python -m unittest tests.<module>` cannot work in this checkout.
# The name `tests` answers .venv/lib/python3.14/site-packages/tests, which is another
# package, so that import never reaches this directory.  The loader then reports
# `ModuleNotFoundError: No module named 'tests.<module>'` for a file that is present.
# Run the module from inside tests/ instead, with the repository on PYTHONPATH.
run_python_module() {
  local module="$1" py="$PYTHON"
  case "$module" in
    *.*) echo "$0: name the module without dots: $module" >&2; exit 2 ;;
  esac
  if [ ! -f "tests/$module.py" ]; then
    echo "$0: no such test module: tests/$module.py" >&2; exit 2
  fi
  case "$py" in /*) ;; *) py="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")" ;; esac
  echo "== python: unittest $module"
  ( cd tests && PYTHONPATH=.. "$py" -m unittest "$module" )
}

run_js() {
  for suite in tests/test_ops.js tests/test_board.js tests/test_app_timeline.js; do
    echo "== node: $suite"
    node "$suite"
  done
}

case "${1:-all}" in
  all)    run_python; run_js ;;
  python) if [ "$#" -ge 2 ]; then run_python_module "$2"; else run_python; fi ;;
  js)     run_js ;;
  *)      echo "usage: $0 [all|python [module]|js]" >&2; exit 2 ;;
esac
