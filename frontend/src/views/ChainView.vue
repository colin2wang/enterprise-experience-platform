<script setup lang="ts">
/* Evolution chain view: topic list + per-topic lane visualization. */

import { onMounted, ref } from "vue";
import { api, pid } from "../api";
import { typeLabel } from "../labels";
import { statusLabel } from "../labels";
import type { Chain, ChainTopic } from "../types";

const topics = ref<ChainTopic[]>([]);
const error = ref("");
const query = ref("");
const chain = ref<Chain | null>(null);

onMounted(async () => {
  try {
    topics.value = await api(`${pid()}/chain/topics`);
  } catch (e: any) {
    error.value = e.message;
  }
});

function filtered(t: ChainTopic) {
  const q = query.value.toLowerCase();
  if (!q) return true;
  return JSON.stringify(t).toLowerCase().includes(q);
}

async function loadChain(expId: string) {
  chain.value = await api(`/experiences/${expId}/chain`);
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else>
    <h2>Evolution Chain</h2>
    <div class="disclaimer">
      Related items do not automatically imply causation or completed verification.
    </div>
    <div class="toolbar"><input v-model="query" placeholder="Search topics..." /></div>
    <table>
      <thead>
        <tr><th>Topic</th><th>Type</th><th>Meetings</th><th>Relations</th></tr>
      </thead>
      <tbody>
        <tr v-for="t in topics.filter(filtered)" :key="t.id" data-exp @click="loadChain(t.id)">
          <td>{{ t.title }}</td>
          <td>{{ typeLabel(t.type) }}</td>
          <td>{{ t.meeting_count }}</td>
          <td>{{ t.relation_count }}</td>
        </tr>
      </tbody>
    </table>
    <div id="chain-view" v-if="chain">
      <h3>Chain: {{ chain.topic }} ({{ chain.relation_count }} relations)</h3>
      <div class="lanes">
        <div v-for="lane in chain.lanes" :key="lane.type" class="lane">
          <h4>{{ typeLabel(lane.type) }} ({{ lane.cards.length }})</h4>
          <template v-if="lane.cards.length">
            <div
              v-for="(c, i) in lane.cards"
              :key="i"
              class="card"
              style="margin-bottom: 8px"
            >
              <span class="code">{{ c.experience.code || "" }}</span>
              <span class="badge" :class="c.experience.status">{{ statusLabel(c.experience.status) }}</span>
              <div class="title">{{ c.experience.title }}</div>
              <div class="meta">{{ c.meeting_date || "" }}</div>
            </div>
          </template>
          <div v-else class="empty">{{ lane.placeholder }}</div>
        </div>
      </div>
    </div>
  </template>
</template>
