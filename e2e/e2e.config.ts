import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';

export default {
  targets: [{
    engine: web(),
    app: {
      url: process.env.APP_URL ?? 'http://127.0.0.1:8130',
      // The console is a static shell served by annotator/unified_server.py; the tests do not
      // start it. Run `python annotator/unified_server.py --port 8130` first.
    },
  }],
  workers: 1,
  // The review test waits up to 60 s for the server to decode the first frame.
  timeout: 180000,
  // A loaded host answers slowly; a locator check may wait 15 s, not the default 5 s.
  assertionTimeout: 15000,
} satisfies E2EConfig;
