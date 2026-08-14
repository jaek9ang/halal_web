import { request } from "./client";

export function getAiRuleReviewStatus() {
  return request("/ai-rule-review/status");
}

export function analyzeAiRuleExport({
  export_path = "",
  limit = 10000,
  max_cases = 20,
  model = "",
  save_candidates = true,
} = {}) {
  return request("/ai-rule-review/analyze-export", {
    method: "POST",
    body: JSON.stringify({
      export_path,
      limit,
      max_cases,
      model,
      save_candidates,
    }),
  });
}

export function getAiRuleProblemCases({
  export_path = "",
  limit = 10000,
  max_cases = 40,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    max_cases: String(max_cases),
  });

  if (export_path) {
    params.set("export_path", export_path);
  }

  return request(`/ai-rule-review/problem-cases?${params.toString()}`);
}

export function getAiRuleCandidates({
  limit = 100,
  apply_status = "",
  target_org = "",
  target_field = "",
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  if (apply_status) params.set("apply_status", apply_status);
  if (target_org) params.set("target_org", target_org);
  if (target_field) params.set("target_field", target_field);

  return request(`/ai-rule-review/candidates?${params.toString()}`);
}

export function validateAiRuleCandidate(rule_candidate_id, {
  export_path = "",
  limit = 10000,
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/validate`, {
    method: "POST",
    body: JSON.stringify({
      export_path,
      limit,
    }),
  });
}

export function applyAiRuleCandidate(rule_candidate_id, {
  validation_report_id = "",
  actor = "user",
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/apply`, {
    method: "POST",
    body: JSON.stringify({
      validation_report_id,
      actor,
    }),
  });
}

export function rejectAiRuleCandidate(rule_candidate_id, {
  reason = "",
  actor = "user",
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/reject`, {
    method: "POST",
    body: JSON.stringify({
      reason,
      actor,
    }),
  });
}

export function getAiRuleValidationReport(validation_report_id) {
  return request(`/ai-rule-review/reports/${encodeURIComponent(validation_report_id)}`);
}
