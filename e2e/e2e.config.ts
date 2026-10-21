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
} satisfies E2EConfig;
