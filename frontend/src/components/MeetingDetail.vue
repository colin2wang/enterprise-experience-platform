<script setup lang="ts">
/* Meeting detail shown inside the drawer. */

import { onMounted, ref } from "vue";
import { api } from "../api";
import { statusLabel } from "../labels";
import type { Meeting } from "../types";
import ExpCard from "./ExpCard.vue";

const props = defineProps<{ meetingId: string }>();

const m = ref<Meeting | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    m.value = await api(`/meetings/${props.meetingId}`);
  } catch (e: any) {
    error.value = e.message;
  }
});
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else-if="m">
    <h2>{{ m.title }}</h2>
    <div>
      <span class="badge" :class="m.review_status">{{ statusLabel(m.review_status) }}</span>
      <span class="meta">{{ m.meet_date || "" }} {{ (m.participants || []).join(", ") }}</span>
    </div>
    <h3>Summary</h3>
    <p>{{ m.summary || "-" }}</p>
    <h3>Discussion</h3>
    <p>{{ m.discussion || "-" }}</p>
    <h3>Related experiences</h3>
    <template v-if="m.related_experiences.length">
      <ExpCard v-for="e in m.related_experiences" :key="e.id" :exp="e" />
    </template>
    <div v-else class="empty-hint">None.</div>
  </template>
</template>
