<script setup lang="ts">
/* Connected services (AI provider health). */

import { onMounted, ref } from "vue";
import { api } from "../api";
import { statusLabel } from "../labels";
import type { ModelInfoEntry, ProviderHealth } from "../types";

const reports = ref<ProviderHealth[]>([]);
const models = ref<ModelInfoEntry[]>([]);
const error = ref("");

async function load() {
  try {
    const [health, info] = await Promise.all([
      api("/admin/ai-providers/health"),
      api("/admin/model-info"),
    ]);
    reports.value = health;
    models.value = info.models;
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
    <h2>Models</h2>
    <table>
      <thead>
        <tr>
          <th>Model</th><th>Vendor</th><th>Capabilities</th><th>Context</th><th>Roles</th><th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in models" :key="m['model-id']">
          <td>
            <span class="mono">{{ m["display-name"] || m.model }}</span>
            <div class="meta">{{ m["model-id"] }}</div>
          </td>
          <td>{{ m.vendor || "-" }}</td>
          <td>{{ m.capabilities.join(", ") || "-" }}</td>
          <td>
            {{ m["context-window"] || "-" }}
            <span
              v-if="m['expected-context'] && m['expected-context'] !== m['context-window']"
              class="meta"
            >(runtime {{ m["expected-context"] }})</span>
          </td>
          <td>
            <template v-if="m.roles.length">
              <span v-for="r in m.roles" :key="r.role" class="badge" :class="r.usage">
                {{ r.role }} ({{ r.usage }})
              </span>
            </template>
            <template v-else>-</template>
          </td>
          <td class="meta">{{ m.description }}</td>
        </tr>
      </tbody>
    </table>
  </template>
</template>
