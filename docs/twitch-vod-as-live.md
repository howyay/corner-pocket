# Twitch VOD replayed as live (2026-09-24 measured)

Owner's decision: **live input = a Twitch VOD replayed as if it were real time.** The live
broadcast path is blocked externally; a recorded VOD is not. This document records what is
actually reachable from this machine, what was built, what was measured, and what stays
unproven.

## 1. What is reachable (raw evidence, verbatim)

**The club's saved channel is `examplechannel`** (`out/corner-pocket/state.json`, read-only;
md5 unchanged by this work). It has one archived broadcast, so no third-party probe VOD was
needed: everything below is the club's own stream, not a probe.

Chain, as recorded by `tests/twitch_vod_realtime_run.py --probe` (tokens, signatures, signed
URLs and the requesting IP are redacted by construction - `evidence()` emits lengths and
hostnames only):

| step | request | result |
|---|---|---|
| 1. channel VODs | `POST https://gql.twitch.tv/gql` `{user(login:"examplechannel"){videos(first:3,type:ARCHIVE){edges{node{id title lengthSeconds createdAt}}}}}` | **HTTP 200**, `errors: null`; one VOD: `id 1000000001`, title `260918`, `lengthSeconds 31137`, `createdAt 2026-09-19T01:29:07Z` |
| 2. playback token | `{video(id:"1000000001"){playbackAccessToken(params:{platform:"web",playerBackend:"mediaplayer",playerType:"site"}){signature value}}}` | **HTTP 200**, `errors: null`, token present (`signature_len 40`, `value_len 444`) |
| 3. usher | `GET https://usher.ttvnw.net/vod/1000000001.m3u8?nauth=…&nauthsig=…&allow_source=true&playlist_include_framerate=true&supported_codecs=avc1` | **HTTP 200**, 5 lines, one variant: `RESOLUTION=1280x720`, `FRAME-RATE=30.000`, `BANDWIDTH=3161420`, `CODECS="avc1.4D001F,mp4a.40.2"` |
| 4. media playlist | the signed variant URL | **HTTP 200**, `#EXT-X-PLAYLIST-TYPE:EVENT`, `#EXT-X-TARGETDURATION:12`, `#ID3-EQUIV-TDTG:2026-09-19T10:08:07`, 53 `#EXTINF` in the first 4 KB, host `d2nvs31859zcd8.cloudfront.net` |
| 5. decode | `cv2.VideoCapture(media_url, CAP_FFMPEG, [open 15 s, read 8 s])` | `isOpened True`, `fps 30.0`, `frames 934137` (≈8.65 h), 1280x720; first read 0.04 s, then 60 frames in 0.10 s = **607 fps free-run** |

Two failures are recorded rather than hidden:

- The plain query form **requires** that explicit `params` argument. Without it Twitch answers
  **HTTP 200** with `errors: [{"message":"argument: params is required on field:
  playbackAccessToken but missing"}]` and a null token - a null token is not a network error.
  The persisted-query shape the live resolver uses returns the same token under
  `data.videoPlaybackAccessToken` instead of `data.video.playbackAccessToken`.
- VOD media is **not** on the live hosts: usher hands out a signed playlist on Twitch's
  CloudFront distribution (`d2nvs31859zcd8.cloudfront.net`), so the live resolver's media
  allowlist (`*.ttvnw.net`, `*.twitchcdn.net`) correctly refuses it. `twitch_vod_source`
  pins that exact host for VOD media (never `*.cloudfront.net`) and keeps the live allowlist
  for API calls.

**Contrast with the live path (recorded 2026-09-24, unchanged):** `usher.ttvnw.net/api/channel/hls/<channel>.m3u8`
answers `404 {"error":"Can not find channel"}` for every channel tried, including 24/7 ones,
with a valid token and with or without a browser user-agent. Streamlink's only extra step is a
client-integrity token acquired by driving a headless browser, which this repository refuses by
design. So: **live broadcast blocked externally, VOD reachable anonymously.** That is exactly
the gap the owner's decision closes.

## 2. What was built

`annotator/twitch_vod_source.py` (no new dependencies):

- **Fetch**: `channel_recent_vods`, `vod_info`, `vod_token`, `vod_variants`, `resolve_vod`
  (best variant ≤720p), plus `_validate_media` and `evidence()` (redaction). Redirects are
  refused; hosts are validated; transport failures are reported by exception *type* only.
- **`VodRealtimeCapture(media, vod_id=…, rate=1.0, start_s=0.0)`**: the wall clock is the
  authority. `read()` returns the frame whose video time is `start_s + rate x (wall clock
  since open)`, *sleeping* while the video is ahead of that line and *dropping source frames*
  (counted) while it is behind, bounded by `max_catchup_s` (default 1 s) per call so a stalled
  consumer recovers over the following reads instead of blocking inside one. A slow consumer
  loses frames; it never falls behind in time.
- **Honest self-description** - never "live": `state()` returns `kind: 'vod-replay'`,
  `live: False`, `vod_id`, `network: 'hls'|'file'`, `rate`, `pacing: 'wall-clock'`, `wall_s`,
  `video_s`, `expected_video_s`, `drift_s`, `frames_served`, `frames_dropped`, `read_failures`.
- **The pipeline file was not touched.** `LiveProcessor` already accepts an injected
  `resolver`/`capture_factory`; the runner uses that seam, so `annotator/live_processing.py`
  and `annotator/pipeline_stages.py` are unchanged by this work.

## 3. Measurements (≥3 minutes of wall clock each)

`tests/twitch_vod_realtime_run.py`, artifacts `out/live-envelope/vod-as-live.json` and
`out/live-envelope/file-as-live.json`. Both runs: 185 s measured window after a 15 s warm-up
that pays the one-time YOLO load, stages `table,person`, budget 33.33 ms enforced. The host
was **shared and busy** (`loadavg` in the table); the last envelope section of
`docs/live-processing-verification.md` has the same pipeline at `loadavg` 4-6 for comparison.

| | Twitch VOD as live | local file as live |
|---|---|---|
| source | VOD `1000000001`, 720p30 HLS, `examplechannel` | `data/vod_30min_260815.mp4` from 267 s || host `loadavg` (1/5/15 min, 12 cores) | 35.5 / 33.3 / 23.8 | 37.0 / 34.6 / 29.0 |
| open (first frame) | 0.7 s | 0.6 s |
| frames received | 5488 (**29.61 fps**) | 5435 (**29.34 fps**) |
| frames published | 3697 (**19.95 fps**) | 671 (**3.62 fps**) |
| drops (no_frame_ready / stage_overrun / stale) | 519 / 1249 / 23 | 1220 / 3452 / 92 |
| partition invariant `processed + Σdrops == received` | **holds** (3697+1791 = 5488) | **holds** (671+4764 = 5435) |
| pacing: video consumed / wall | 185.30 s / 185.35 s = **0.9997 x** | 185.23 s / 185.21 s = **1.0001 x** |
| pacing drift (end / max) | **-0.09 s / 0.24 s** | **-0.01 s / 1.76 s** |
| frames dropped by the pacer | 70 | 121 |
| `table` p50 / p95 / max ms | 0.02 / 0.03 / 13.28 | 0.02 / 0.04 / 19.51 |
| `person` p50 / p95 / max ms | 15.50 / 31.05 / 676.0 | 23.76 / 75.55 / 207.18 |
| `decode` p50 / p95 / max ms | 33.26 / 38.41 / 166.99 | 33.17 / 44.29 / 55.66 |
| `resize` p50 / p95 / max ms | 6.45 / 11.10 / 20.35 | 9.04 / 23.92 / 41.03 |
| `encode` p50 / p95 / max ms | 1.88 / 2.84 / 6.35 | 1.95 / 7.22 / 13.32 |
| `receive_to_result` p50 / p95 / max ms | 25.71 / 43.89 / 683.97 | 49.56 / 103.55 / 266.57 |

**What the invariant and the pacing rows do not say.** The frames are a recording that was
already days old when it was played back: the VOD above was created `2026-09-19` and
replayed on `2026-09-24`. Only the pacing is wall-clock. Nothing in this table is evidence
that a *live* broadcast can be received - that path still answers `404` (§1) - and every
surface of the module says so: `state()` returns `kind: 'vod-replay'`, `live: False`, and
the UI label is `TWITCH VOD · RECORDED VIDEO`. Three conditions bound the result, all
outside this repository's control: the channel must still list an archived VOD
(`channel_recent_vods` asks Twitch for `type: ARCHIVE`); Twitch must still issue a playback
token for that VOD (a deleted, expired or subscriber-only VOD ends here); and the media
playlist must still be an `EVENT`/`VOD` playlist on the pinned CloudFront host. When any of
them fails the capture reports the failure and counts `read_failures`; it never invents
frames. And "1x" is about the source, not the output: both runs are 185 s on one shared,
busy host (1-min `loadavg` 35.5 and 37.0), where the published rate was 19.95 fps (VOD) and
3.62 fps (file).

Reading of these numbers, honestly stated:

- **The 1x requirement is met**: 185.3 s of video in 185.4 s of wall clock, drift -0.09 s
  (VOD) and -0.01 s (file), worst excursion 0.24 s / 1.76 s. A consumer cannot tell the
  difference **in pacing** between this and a live feed, and the source says which one it
  is; in content it can, because the picture is a recording (see the paragraph above the
  table).
  (The vod run starts at 0 s, so its `video_s` *is* the consumed amount; the file run starts
  at 267 s, and `video_consumed_s = video_s - start_s` is reported separately. The first
  artifact was written before that field existed, hence its `video_per_wall` reads from
  `video_s` directly - correct there because the offset is zero.)
- **The pipeline holds the source rate** (`received` ≈ 29.3-29.6 fps of a 30 fps source, i.e.
  no accumulating backlog) but **does not publish every frame on this host**: 19.95 fps at
  `loadavg` 35, and only 3.62 fps in the file run at `loadavg` 37, because the person stage
  (15.5 / 23.8 ms p50) plus the CPU steps (resize 6.5-9.0 ms, encode ~2 ms) plus thread
  wake-up jitter exceed the 33.33 ms budget. The missing frames are **counted drops, not
  latency**: `stage_overrun` 1249 / 3452, and the partition invariant holds in both runs.
- **`table` is effectively free on the live path too** (p50 0.02 ms): a live-shaped source
  reports no media position to `live_processing`, so the saved per-segment reference cannot be
  resolved and the stage falls back to its own 30-frame measurement cadence
  (`table_source: 'measured'`, `table_age_frames` up to 25). The ~11 ms/frame win survives
  either way; only the provenance label differs (`saved:vod30-s1` on a dataset replay,
  `measured` here).
- **On a quiet host the same stage mix fits**: the earlier matrix at `loadavg` 4-6 measured
  `table+person` at 14.95 ms p50 (90/90 published, 30.4 fps). The difference between that and
  these runs is the host, not the source.

## 4. What is a probe, what is measured, what is unproven

- **Probe**: `--probe` prints the reachability evidence above and nothing else; it is the only
  network-touching mode with no pipeline. The VOD used is the club's own newest archived
  broadcast, not a third-party probe stream.
- **Measured**: 1x pacing fidelity, per-stage latency, receive-to-result, drop reasons with the
  partition invariant, and the achieved rates - on the real Twitch VOD and on a local file
  through the identical pacing path.
- **Unproven**:
  - **Real broadcast latency.** `upstream_delay_ms` is still `None`: nothing here measures
    glass-to-glass, because a VOD has no encoder, no ingest and no delivery latency. A VOD
    replay proves the *pipeline* end, never the *broadcast* end.
  - Whether a live broadcast behaves like this replay. The decode path is the same codec and
    frame rate, but live HLS is delivered in 2-12 s segments as they are produced, and its
    playlist reloads can stall differently.
  - The ball detector's real cost - still a stand-in (`sleep(15 ms)`), so any fps conclusion
    that includes it is provisional.
  - The saved per-segment table reference on a live-shaped source: `live_processing` reads the
    media position only for dataset replays, so the reference is unused here. The wiring is
    one line (read `CAP_PROP_POS_FRAMES` for any source that reports a finite position); it was
    not made in this round because that file is owned by another worker until it lands.
  - The host's own state: every number above carries `loadavg` 34-37 on 12 cores, with other
    agents' jobs running. The file-mode run is the noisier of the two for that reason.
