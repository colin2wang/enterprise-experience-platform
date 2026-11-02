/* Shared API helpers and reactive project state. */

import { ref } from "vue";

export const projectId = ref(
  localStorage.getItem("eep_project_id") || "00000000-0000-0000-0000-000000000001",
);

export function setProjectId(id: string): void {
  projectId.value = id.trim();
  localStorage.setItem("eep_project_id", projectId.value);
}

export async function api(path: string, options: RequestInit = {}): Promise<any> {
  const resp = await fetch(`/v1${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export const pid = () => `/projects/${encodeURIComponent(projectId.value)}`;
