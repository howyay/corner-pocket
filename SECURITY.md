# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately**, through GitHub's private
vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability** (GitHub Security Advisories). Do not open a public
issue, pull request or discussion for a security problem.

Include what you found, the steps to reproduce it, the commit you tested, and
the impact you expect. We will acknowledge the report, and we will credit you
in the advisory if you wish.

This is a small volunteer project. There is **no bug bounty**, and there are
no guaranteed response times.

## Supported versions

Only the latest commit on `main` is supported. There are no releases or
backports.

## Scope

In scope:

- the code in this repository: the web server and its JSON API
  (`annotator/unified_server.py`), the browser UI (`annotator/`), the vision
  pipeline (`src/`), and `scripts/`;
- for example: path traversal, cross-site scripting, cross-site request
  forgery, server-side request forgery, injection, unsafe file handling, and
  anything that exposes or corrupts stored data, including the biometric data
  (face and body embeddings) under `out/`.

Out of scope:

- **The lack of built-in authentication.** The server has none by design. It
  listens on `127.0.0.1` by default, and any deployment that other people can
  reach must sit behind an authenticating reverse proxy. Reports that an
  unauthenticated server exposed to a network can be used are expected
  behaviour, not vulnerabilities. A way around the proxy, or an attack from
  another origin in the user's browser, is in scope.
- Vulnerabilities in third-party packages or models (for example ultralytics,
  PyTorch, OpenCV, InsightFace, SAM 3). Report those upstream. Tell us if this
  project uses one in a way that makes it exploitable.
- Twitch's endpoints and services, and any deployment we do not operate.
- Denial of service that needs an authenticated user, and findings from
  automated scanners without a demonstrated impact.
