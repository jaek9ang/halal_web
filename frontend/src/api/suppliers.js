import { request } from "./client";

export function getSupplierEmailReview() {
  return request("/suppliers/email-review");
}

export function saveSupplierEmailOverride(payload) {
  return request("/suppliers/email-overrides", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
