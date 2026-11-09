// Replays a recorded traffic profile (RPS per bucket) against the demo app.
import http from 'k6/http';
import { sleep } from 'k6';

const profile = JSON.parse(open(__ENV.PROFILE || '../traffic/profile.json'));
const TARGET = __ENV.TARGET || 'http://localhost:8080';
const BUCKET = Number(__ENV.BUCKET_SECONDS || profile.replay_bucket_seconds || 60);
const SCALE = Number(__ENV.RPS_SCALE || 1);
const START_EPOCH_MS = Number(__ENV.START_EPOCH_MS || 0);
const RAMP = Math.max(1, Math.floor(Math.min(5, BUCKET / 4)));

const stages = [];
for (const rps of profile.rps) {
  const target = Math.round(rps * SCALE);
  stages.push({ target, duration: `${RAMP}s` });
  stages.push({ target, duration: `${BUCKET - RAMP}s` });
}

export const options = {
  setupTimeout: '300s',
  scenarios: {
    replay: {
      executor: 'ramping-arrival-rate',
      startRate: stages[0].target,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 1000,
      stages,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

// Hold the replay until a shared wall-clock instant so cron windows line up with the traffic.
export function setup() {
  while (START_EPOCH_MS && Date.now() < START_EPOCH_MS) {
    sleep(0.2);
  }
}

export default function () {
  http.get(`${TARGET}/work`, { timeout: '10s' });
}
