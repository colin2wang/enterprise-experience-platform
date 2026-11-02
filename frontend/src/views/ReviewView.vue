<script setup lang="ts">
/* Extraction review queue. */

import { onMounted, ref } from "vue";
import { api, pid } from "../api";
import { typeLabel } from "../labels";
import type { ReviewItem } from "../types";

const queue = ref<ReviewItem[]>([]);
const error = ref("");

interface DraftState {
  title: string;
  description: string;
  rejectReason: string;
  showingReason: boolean;
}

const drafts = ref<Record<string, DraftState>>({});

function draftOf(item: ReviewItem): DraftState {
  if (!drafts.value[item.thread_id]) {
    drafts.value[item.thread_id] = {
      title: item.draft.title,
      description: item.draft.description || "",
      rejectReason: "",
      showingReason: false,
    };
  }
  return drafts.value[item.thread_id];
}

onMounted(async () => {
  try {
    queue.value = await api(`${pid()}/review/queue`);
  } catch (e: any) {
    error.value = e.message;
  }
});

function span(item: ReviewItem) {
  return item.draft.source?.span || {};
}

async function submit(item: ReviewItem, decision: "accept" | "accept_edited" | "reject") {
  const d = draftOf(item);
  if (decision === "reject" && !d.showingReason) {
    d.showingReason = true;
    return;
  }
  try {
    await api(`/review/${encodeURIComponent(item.thread_id)}/submit`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reason: decision === "reject" ? d.rejectReason : null,
        edited:
          decision === "accept_edited"
            ? { type: "decision", title: d.title, description: d.description }
            : null,
      }),
    });
    queue.value = queue.value.filter((q) => q.thread_id !== item.thread_id);
  } catch (e: any) {
    alert(e.message);
  }
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else>
    <h2>Extraction Review</h2>
    <template v-if="queue.length">
      <div v-for="item in queue" :key="item.thread_id" class="review-item" data-thread>
        <span class="code mono">{{ item.thread_id }}</span>
        <dl class="kv">
          <dt>Type</dt><dd>{{ typeLabel(item.draft.type) }}</dd>
          <dt>Title</dt><dd><input v-model="draftOf(item).title" class="field rv-title" /></dd>
          <dt>Description</dt><dd><textarea v-model="draftOf(item).description" class="rv-desc"></textarea></dd>
          <dt>Confidence</dt><dd>{{ item.draft.confidence ?? "-" }}</dd>
        </dl>
        <pre v-if="span(item).quote" class="quote">[{{ span(item).start }}-{{ span(item).end }}] {{ span(item).quote }}</pre>
        <div v-if="item.similar?.length" class="meta">
          Similar in library: {{ item.similar.map((s) => s.title).join("; ") }}
        </div>
        <div class="review-actions">
          <button class="primary" @click="submit(item, 'accept')">Accept</button>
          <button @click="submit(item, 'accept_edited')">Accept after edit</button>
          <button @click="submit(item, 'reject')">Reject</button>
        </div>
        <div v-show="draftOf(item).showingReason">
          <textarea v-model="draftOf(item).rejectReason" placeholder="Rejection reason (required)"></textarea>
        </div>
      </div>
    </template>
    <div v-else class="empty-hint">Queue is empty. Everything reviewed.</div>
  </template>
</template>
