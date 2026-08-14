import { request } from "./client";

export function getHealth() {
  return request("/health");
}
