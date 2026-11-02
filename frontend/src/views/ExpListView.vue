<script setup lang="ts">
/* Experience list shared by "Experience Library" and "Action Follow-up". */

import { onMounted, ref, watch } from "vue";
import { api, pid } from "../api";
import { STATUS_LABEL, typeLabel } from "../labels";
import type { Experience } from "../types";
import ExperienceDetail from "../components/ExperienceDetail.vue";
import { openDrawer } from "../drawer";

const props = defineProps<{ kind: string }>();

const exps = ref<Experience[]>([]);
const error = ref("");
const q = ref("");
const status = ref("");
const typeFilter = ref("");

const isAction = () => props.kind === "actions";

async function load() {
  try {
    exps.value = await api(
      `${pid()}/experiences${isAction() ? "?type=action" : ""}`,
    );
  } catch (e: any) {
    error.value = e.message;
  }
}

async function apply() {
  try {
    exps.value = await api(
      `${pid()}/experiences?type=${typeFilter.value}&status=${status.value}&q=${encodeURIComponent(q.value)}`,
    );
  } catch (e: any) {
    error.value = e.message;
  }
}

onMounted(load);

watch(() => props.kind, load);

function openDetail(id: string) {
  openDrawer(ExperienceDetail, { experienceId: id });
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else>
    <h2>{{ isAction() ? "Action Follow-up" : "Experience Library" }}</h2>
    <div v-if="!isAction()" id="type-tabs" class="toolbar">
      <button
        v-for="t in ['', 'question', 'hypothesis', 'experiment', 'decision', 'action']"
        :key="t"
        :data-type="t"
        @click="typeFilter = t; apply()"
      >
        {{ t ? typeLabel(t) : "All" }}
      </button>
    </div>
    <div class="toolbar">
      <input v-model="q" placeholder="Search..." @input="apply" />
      <select v-model="status" @change="apply">
        <option value="">Any status</option>
        <option v-for="(v, k) in STATUS_LABEL" :key="k" :value="k">{{ v }}</option>
      </select>
    </div>
    <table>
      <thead>
        <tr>
          <th>Type · Title</th><th>Status</th><th>Owner</th>
          <th v-if="isAction()">Due date</th>
          <th>Latest source</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in exps" :key="e.id" data-exp @click="openDetail(e.id)">
          <td>
            <span class="mono">{{ typeLabel(e.type) }}</span> {{ e.title }}
            <div class="meta">{{ e.code || "" }}</div>
          </td>
          <td><span class="badge" :class="e.status">{{ STATUS_LABEL[e.status] || e.status }}</span></td>
          <td>
            <template v-if="e.owner_name">{{ e.owner_name }}</template>
            <span v-else class="badge unclaimed">Unclaimed</span>
          </td>
          <td v-if="isAction()">{{ e.due_date || "TBD" }}</td>
          <td class="mono">{{ (e.source_meeting_id || "-").slice(0, 8) }}</td>
        </tr>
      </tbody>
    </table>
  </template>
</template>
