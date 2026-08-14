import { request } from "./client";

export function getMailTargets({
  testMode = true,
  testReceiver = "jaek_ing@naver.com",
} = {}) {
  const params = new URLSearchParams({
    test_mode: String(testMode),
    test_receiver: testReceiver,
  });

  return request(`/mail/targets?${params.toString()}`);
}

export function sendMailRequests(payload) {
  return request("/mail/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMailLogs({ limit = 100, testMode = null } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  if (testMode !== null) {
    params.set("test_mode", String(testMode));
  }

  return request(`/mail/logs?${params.toString()}`);
}

export function hideMailLogs({ ids, includeReal = false }) {
  return request("/mail/logs/hide", {
    method: "POST",
    body: JSON.stringify({
      ids,
      include_real: includeReal,
    }),
  });
}
