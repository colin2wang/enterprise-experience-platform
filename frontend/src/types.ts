/* Frontend data shapes for the EEP API. */

export interface Experience {
  id: string;
  code: string | null;
  type: string;
  title: string;
  status: string;
  owner_name: string | null;
  due_date: string | null;
  acceptance_criteria: string | null;
  source_meeting_id: string | null;
  source_span?: { quote?: string } | null;
}

export interface Meeting {
  id: string;
  title: string;
  meet_date: string | null;
  participants: string[] | null;
  review_status: string;
  summary: string | null;
  discussion: string | null;
  related_experiences: Experience[];
  exp_stat_cache?: {
    total?: number;
    type_distribution?: Record<string, number>;
  } | null;
}

export interface ReviewItem {
  thread_id: string;
  draft: {
    type: string;
    title: string;
    description: string | null;
    confidence: number | null;
    source?: { span?: { start?: string; end?: string; quote?: string } } | null;
  };
  similar: { title: string }[] | null;
}

export interface Overview {
  metrics: {
    effective_decisions: number;
    open_actions: number;
    total_experiences: number;
    total_meetings: number;
  };
  attention_list: Experience[];
  pilots: Experience[];
  decision_quotes: Experience[];
}

export interface ChainTopic {
  id: string;
  title: string;
  type: string;
  meeting_count: number;
  relation_count: number;
}

export interface Chain {
  topic: string;
  relation_count: number;
  lanes: {
    type: string;
    placeholder: string;
    cards: {
      experience: Experience;
      meeting_date: string | null;
    }[];
  }[];
}

export interface ProviderHealth {
  provider: string;
  status: string;
  breaker_state: string | null;
  chat_model_ready: boolean;
  detail: string | null;
}

export interface ModelInfoEntry {
  "model-id": string;
  provider: string;
  model: string;
  "display-name": string;
  vendor: string;
  description: string;
  capabilities: string[];
  "context-window": number;
  "expected-context": number;
  roles: { role: string; usage: string }[];
}
