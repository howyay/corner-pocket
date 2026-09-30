# FFmpeg pin

Event clips (`GET /api/clip`) and VOD imports (`/api/vods/import`) both run FFmpeg.
The service's `PATH` has no `ffmpeg` and no `ffprobe`, so the binaries are named
explicitly, and the name is a path that survives `nix-collect-garbage`.

## The problem this replaced

`Backend._ffmpeg()` (`annotator/unified_server.py`) fell back to the newest
`/nix/store/*-ffmpeg-headless-*-bin/bin/ffmpeg`, and `annotator/vod_import.py` took
`ffprobe` from beside it. Those store paths are **not** rooted: the next
`nix-collect-garbage` deletes the build and both features stop working (an honest 503,
but broken).

## The stable path

```
~/.local/state/pool/ffmpeg-bin -> /nix/store/cjsxh3v95ki1mwcccya9zhfdc837703c-ffmpeg-headless-9.0-bin
```

Both binaries are there: `~/.local/state/pool/ffmpeg-bin/bin/ffmpeg` and `.../bin/ffprobe`.

It is a GC root, so the collector keeps the build. Proof (no real GC is run):

```
$ nix-store -q --roots ~/.local/state/pool/ffmpeg-bin
/home/operator/.local/state/pool/ffmpeg-bin -> /nix/store/cjsxh3v95ki1mwcccya9zhfdc837703c-ffmpeg-headless-9.0-bin
$ nix-store --gc --print-roots | grep ffmpeg-bin
"/home/operator/.local/state/pool/ffmpeg-bin" -> /nix/store/cjsxh3v95ki1mwcccya9zhfdc837703c-ffmpeg-headless-9.0-bin
```

Method: a user-level GC root (the dotfiles' NixOS config is not touched; if the user
environment ever becomes declarative, the same path can be produced by
`home-manager` and this document stays valid).

## How the app uses it

The systemd drop-in template lives in the repository and is **not** installed by this
change (`deploy/systemd/pool-workbench.service.d/30-ffmpeg.conf`):

```ini
[Service]
Environment=POOL_FFMPEG=%h/.local/state/pool/ffmpeg-bin/bin/ffmpeg
Environment=POOL_FFPROBE=%h/.local/state/pool/ffmpeg-bin/bin/ffprobe
```

Install it with `cp deploy/systemd/pool-workbench.service.d/30-ffmpeg.conf
~/.config/systemd/user/pool-workbench.service.d/` then `systemctl --user daemon-reload`
and restart. `20-postgres.conf` is untouched, and an explicit variable is preferred over
rewriting `PATH`, which would risk dropping entries the service needs.

`annotator/ffmpeg_bin.py` is the single resolver, used by the clip path
(`ServerBackend._ffmpeg()`) and by the importer (`default_ffmpeg_command()`,
`ffprobe_beside()`). Order:

1. `POOL_FFMPEG` / `POOL_FFPROBE` when set;
2. the sibling of the resolved `ffmpeg` (same build, so the same version);
3. `PATH`;
4. the newest `/nix/store/*-ffmpeg-headless-*-bin` build - dev fallback only, and the
   comment on `STORE` says why it is fragile.

When a variable is set and its file is missing, the resolver raises
`MediaBinaryMissing` and the caller answers **503 naming the variable** - there is no
silent fallback, because a fallback would hide exactly the broken deployment this pin
exists to prevent.

Note on names: `POOL_FFMPEG` and `POOL_FFPROBE` are ordinary paths, not a store
switch. The rule other suites assert is "no `POOL_DATABASE_URL`", not "no `POOL_*`".

Tests: `tests/test_ffmpeg_bin.py`.
