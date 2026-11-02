<script setup lang="ts">
/* Experience detail shown inside the drawer, with claim + chain actions. */

import { onMounted, ref } from "vue";
import { api } from "../api";
import { statusLabel, typeLabel } from "../labels";
import type { Experience } from "../types";
import { closeDrawer } from "../drawer";

const props = defineProps<{ experienceId: string }>();

const e = ref<Experience | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    e.value = await api(`/experiences/${props.experienceId}`);
  } catch (err: any) {
    error.value = err.message;
  }
});

async function claim() {
  const owner = prompt("Owner ID (UUID) to assign:");
  if (!owner) return;
  await api(`/experiences/${props.experienceId}/claim?owner_id=${encodeURIComponent(owner)}`, {
    method: "POST",
  });
  closeDrawer();
}

function viewChain() {
  closeDrawer();
  window.dispatchEvent(new CustomEvent("eep:navigate", { detail: "chain" }));
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else-if="e">
    <h2>{{ e.title }}</h2>
    <div>
      <span class="code mono">{{ e.code || e.id.slice(0, 8) }}</span>
      <span class="badge" :class="e.status">{{ statusLabel(e.status) }}</span>
    </div>
    <dl class="kv">
      <dt>Type</dt><dd>{{ typeLabel(e.type) }}</dd>
      <dt>Owner</dt><dd>{{ e.owner_name || "Unclaimed" }}</dd>
      <dt>Due date</dt><dd>{{ e.due_date || "TBD" }}</dd>
      <dt>Acceptance</dt><dd>{{ e.acceptance_criteria || "-" }}</dd>
      <dt>Source span</dt>
      <dd>
        <pre v-if="e.source_span?.quote" class="quote">{{ e.source_span.quote }}</pre>
        <template v-else>-</template>
      </dd>
    </dl>
    <div class="review-actions">
      <button id="claim-btn" @click="claim">Claim</button>
      <button id="chain-btn" @click="viewChain">View evolution chain</button>
    </div>
  </template>
</template>
