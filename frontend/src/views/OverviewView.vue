<script setup lang="ts">
/* Decision Overview view. */

import { onMounted, ref } from "vue";
import { api, pid } from "../api";
import type { Overview } from "../types";
import ExpCard from "../components/ExpCard.vue";

const data = ref<Overview | null>(null);
const error = ref("");
const briefing = ref<string | null>(null);
const seeding = ref(false);
const seedNote = ref("");

async function loadOverview() {
  data.value = await api(`${pid()}/overview`);
}

onMounted(async () => {
  try {
    await loadOverview();
  } catch (e: any) {
    error.value = e.message;
  }
});

async function seedDemo() {
  seeding.value = true;
  seedNote.value = "";
  try {
    const out = await api("/internal/seed-demo", { method: "POST" });
    seedNote.value = `Demo data loaded: ${out.meetings} meetings, ${out.experiences} experiences.`;
    await loadOverview();
  } catch (e: any) {
    seedNote.value = `Seeding failed: ${e.message}`;
  } finally {
    seeding.value = false;
  }
}

async function exportBriefing() {
  const out = await api(`${pid()}/briefing`, { method: "POST" });
  briefing.value = out.briefing_markdown || "(empty)";
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else-if="data">
    <h2>Decision Overview</h2>
    <div v-if="data.metrics.total_meetings === 0" class="empty-hint" style="margin-bottom: 14px">
      The database is empty. You can add a real meeting, or
      <button :disabled="seeding" @click="seedDemo">{{ seeding ? "Loading demo data..." : "Load demo data" }}</button>
      to explore the platform with a seeded example project.
      <div v-if="seedNote" class="meta" style="margin-top: 6px">{{ seedNote }}</div>
    </div>
    <div class="metrics">
      <div class="metric"><b>{{ data.metrics.effective_decisions }}</b><span>Effective decisions</span></div>
      <div class="metric"><b>{{ data.metrics.open_actions }}</b><span>Open actions</span></div>
      <div class="metric"><b>{{ data.metrics.total_experiences }}</b><span>Experiences</span></div>
      <div class="metric"><b>{{ data.metrics.total_meetings }}</b><span>Meetings</span></div>
    </div>

    <h3>Needs confirmation this time</h3>
    <div class="cards">
      <ExpCard v-if="data.attention_list.length" v-for="e in data.attention_list" :key="e.id" :exp="e" />
      <div v-else class="empty-hint">Nothing pending confirmation.</div>
    </div>

    <h3>Current pilot scope</h3>
    <div class="cards">
      <ExpCard v-if="data.pilots.length" v-for="e in data.pilots" :key="e.id" :exp="e" />
      <div v-else class="empty-hint">No planned experiments.</div>
    </div>

    <h3>Decisions are traceable</h3>
    <div class="cards">
      <ExpCard v-if="data.decision_quotes.length" v-for="e in data.decision_quotes" :key="e.id" :exp="e" />
      <div v-else class="empty-hint">No effective decisions yet.</div>
    </div>

    <div style="margin-top: 16px">
      <button class="primary" @click="exportBriefing">Export pre-meeting briefing</button>
      <pre
        v-if="briefing !== null"
        style="margin-top: 10px; white-space: pre-wrap; background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 14px"
      >{{ briefing }}</pre>
    </div>
  </template>
</template>
