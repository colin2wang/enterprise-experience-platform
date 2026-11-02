/* Shared label maps. */

export const TYPE_LABEL: Record<string, string> = {
  question: "Question",
  hypothesis: "Hypothesis",
  experiment: "Experiment",
  decision: "Decision",
  action: "Action",
};

export const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  in_progress: "In Progress",
  planned: "Planned",
  effective: "Effective",
  invalid: "Invalid",
  completed: "Completed",
};

export const typeLabel = (t: string) => TYPE_LABEL[t] || t;
export const statusLabel = (s: string) => STATUS_LABEL[s] || s;
