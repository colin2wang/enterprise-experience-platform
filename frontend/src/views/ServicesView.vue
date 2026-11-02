<script setup lang="ts">
/* Connected services (AI provider health). */

import { onMounted, ref } from "vue";
import { api } from "../api";
import { statusLabel } from "../labels";
import type { ProviderHealth } from "../types";

const reports = ref<ProviderHealth[]>([]);
const error = ref("");

async function load() {
  try {
    reports.value = await api("/admin/ai-providers/health");
  } catch (e: any) {
    error.value = e.message;
  }
}

onMounted(load);

async function reloadConfig() {
  await api("/internal/ai-config/reload", { method: "POST" });
  await load();
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else>
    <h2>Connected Services</h2>
    <div class="toolbar">
      <button class="primary" @click="reloadConfig">Reload AI config</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>Provider</th><th>Status</th><th>Breaker</th><th>Chat model ready</th><th>Detail</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in reports" :key="r.provider">
          <td class="mono">{{ r.provider }}</td>
          <td><span class="badge" :class="r.status">{{ statusLabel(r.status) }}</span></td>
          <td>{{ r.breaker_state || "-" }}</td>
          <td>{{ r.chat_model_ready ? "yes" : "no" }}</td>
          <td class="meta">{{ r.detail || "" }}</td>
        </tr>
      </tbody>
    </table>
  </template>
</template>
