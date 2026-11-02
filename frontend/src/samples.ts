/* Sample meeting transcripts for the "Add meeting" form.
   Users can pick one to prefill the form, then edit before submitting. */

export interface MeetingSample {
  name: string;
  title: string;
  meetDate: string;
  participants: string;
  transcript: string;
}

export const MEETING_SAMPLES: MeetingSample[] = [
  {
    name: "Sprint planning",
    title: "Sprint 42 Planning",
    meetDate: "2026-11-02",
    participants: "Alice Johnson, Brian Miller, Chen Xiaoyun",
    transcript: `Alice: Let's plan sprint 42. The main theme is the ticket-search quality improvement.
Brian: Last sprint we shipped the basic keyword search, but relevance is still poor. Support tickets mention it twice a day.
Alice: Decision: we will prioritize semantic search over the relevance-score tuning this sprint. Rationale: customer impact is higher.
Brian: Action: I will prototype the embedding-based search and validate it against the top-50 real ticket queries by Friday.
Chen: Question: do we keep the keyword fallback when the embedding service is down?
Alice: Decision: yes, keyword search stays as a fallback. Availability beats a small relevance gain.
Chen: Action: I will add the fallback switch and a health probe for the embedding service.
Alice: Action: I will draft the rollout plan and share it with support for review next Monday.
Brian: Note: the evaluation set needs manual labels. Hypothesis: 50 labeled queries are enough for a first pass.
Alice: Agreed. Let's review the labels together on Wednesday.`,
  },
  {
    name: "Incident retrospective",
    title: "Incident Retro: Checkout Outage (Oct 28)",
    meetDate: "2026-10-30",
    participants: "Derek Wu, Elena Petrova, Frank Adler",
    transcript: `Derek: Summary of the outage: checkout was down 38 minutes on Oct 28. Root cause was a connection-pool exhaustion after the price-cache change.
Elena: The deploy removed the cache TTL but kept the old invalidation loop, so every request opened a new connection.
Derek: Decision: all schema-adjacent config changes require a second reviewer from the platform team before deploy.
Frank: Question: why did the alert fire only after customer reports? The dashboard showed pool saturation nine minutes earlier.
Elena: Answer: the alert threshold was set at 100% saturation. Action: I will lower it to 80% and add a 5-minute sustained window.
Frank: Action: I will write the runbook entry for connection-pool exhaustion, including the emergency restart procedure.
Derek: Action: I will schedule the failover drill for next sprint and report the result in the ops review.
Elena: Lesson: the invalidation loop tests mocked the cache client, so the regression never showed up. Hypothesis: an integration test against a real Redis instance would have caught it.`,
  },
  {
    name: "Design review",
    title: "Design Review: Unified Ticket Taxonomy",
    meetDate: "2026-11-01",
    participants: "Grace Liu, Henry Adams, Ivy Chen",
    transcript: `Grace: Today we review the unified ticket taxonomy proposal. Goal: one tag set across support, product, and engineering.
Henry: The current draft has 12 top-level categories. Risk: too granular for support agents to pick quickly.
Grace: Decision: we cap the top level at 8 categories and move the rest to a second-level tag. Rationale: agents must tag in under 10 seconds.
Ivy: Question: how do we handle tickets that span two categories, like billing and refund?
Grace: Decision: primary category is single-select; the second-level tag is multi-select. No duplicate primary categories.
Henry: Action: I will map the existing 240 legacy tags onto the new taxonomy and flag conflicts by Thursday.
Ivy: Action: I will run a tagging trial with five support agents and measure misclassification rate.
Grace: Decision: we adopt the taxonomy only if the trial misclassification rate stays under 15%.
Frank: Note: the migration must be reversible. Action: Grace will draft the rollback plan before we touch production data.`,
  },
  {
    name: "Customer feedback sync",
    title: "Customer Feedback Sync: Enterprise Accounts",
    meetDate: "2026-10-29",
    participants: "Alice Johnson, Karen White, Leo Martins",
    transcript: `Karen: Three enterprise accounts asked for SSO this month. It is now the top blocker for two renewals.
Leo: The pilot accounts also complain about the export being limited to 1000 rows.
Alice: Decision: SSO goes into the next quarterly plan; the export limit increase is a quick win we ship this month.
Karen: Action: I will collect the exact renewal dates and SSO requirements (SAML vs OIDC) from the three accounts by Wednesday.
Leo: Action: I will raise the export limit to 50,000 rows and add pagination, behind a feature flag.
Alice: Question: what is the effort estimate for SAML?
Leo: Hypothesis: two engineer-weeks with the identity library we already use. I will confirm after a spike.
Karen: Risk: one account wants SCIM user provisioning too. If we promise SSO without SCIM, the renewal may still stall.
Alice: Decision: scope SSO first; SCIM is a follow-up, and Karen communicates the timeline to the account before the renewal call.`,
  },
  {
    name: "Architecture sync",
    title: "Architecture Sync: Notification Service Extraction",
    meetDate: "2026-10-27",
    participants: "Brian Miller, Elena Petrova, Henry Adams",
    transcript: `Brian: Goal today: agree on the plan to extract the notification service from the monolith.
Elena: Currently 14 call sites send notifications inline. That couples deploys and causes duplicated emails during retries.
Brian: Decision: we extract behind an internal API first, no message queue in phase one. Rationale: lowest migration risk.
Henry: Question: do we keep the template rendering in the monolith or move it too?
Brian: Decision: move rendering into the new service. Half-done extraction is worse than a clean cut.
Elena: Action: I will inventory the 14 call sites and classify them by notification type within three days.
Henry: Action: I will draft the API contract (send, schedule, cancel) and circulate it for review.
Brian: Risk: the marketing team has a parallel bulk-mail initiative. Hypothesis: we can reuse their provider account configuration.
Elena: Action: I will sync with marketing before the contract review to avoid two competing abstractions.`,
  },
];
