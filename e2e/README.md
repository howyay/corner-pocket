# Console end-to-end tests

The tests drive the running console with a real browser. Start the console first.

```sh
python annotator/unified_server.py --port 8130 --public-port 8132 --public-prefix /board
./e2e/scripts/run-local.sh
```

`run-local.sh` sets `LD_LIBRARY_PATH` from the nix store, because the Playwright
chromium binary does not find glib and the other shared libraries on this host.

The suite covers six user features: the shell and its six tabs, the competition
card (name, pencil, one button row, rename), the shot timer, the History review
stage, the Livestream panel, and the public board.
