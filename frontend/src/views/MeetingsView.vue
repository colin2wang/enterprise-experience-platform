<script setup lang="ts">
/* Meetings view: list + detail drawer + "add meeting" (transcript push). */

import { onMounted, ref } from "vue";
import { api, projectId } from "../api";
import { statusLabel } from "../labels";
import type { Meeting } from "../types";
import MeetingDetail from "../components/MeetingDetail.vue";
import { openDrawer } from "../drawer";

const meetings = ref<Meeting[]>([]);
const error = ref("");
const query = ref("");

const projectIdParam = () => encodeURIComponent(projectId.value);

async function load() {
  try {
    meetings.value = await api(`/projects/${projectIdParam()}/meetings`);
  } catch (e: any) {
    error.value = e.message;
  }
}

onMounted(load);

function filtered(m: Meeting) {
  const q = query.value.toLowerCase();
  if (!q) return true;
  return JSON.stringify(m).toLowerCase().includes(q);
}

function openDetail(id: string) {
  openDrawer(MeetingDetail, { meetingId: id });
}

/* ---- Add meeting (transcript push, triggers G1 ingestion) ---- */
const showForm = ref(false);
const submitting = ref(false);
const formError = ref("");
const form = ref({ title: "", meet_date: "", participants: "", transcript_text: "" });

function toggleForm() {
  showForm.value = !showForm.value;
  formError.value = "";
}

async function submitMeeting() {
  if (!form.value.title.trim() || !form.value.transcript_text.trim()) {
    formError.value = "Title and transcript are required.";
    return;
  }
  submitting.value = true;
  formError.value = "";
  try {
    await api(`/projects/${projectIdParam()}/meetings`, {
      method: "POST",
      body: JSON.stringify({
        title: form.value.title.trim(),
        meet_date: form.value.meet_date || null,
        participants: form.value.participants
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        source_type: "upload",
        transcript_text: form.value.transcript_text,
        pipeline_version: "v1",
      }),
    });
    showForm.value = false;
    form.value = { title: "", meet_date: "", participants: "", transcript_text: "" };
    await load();
  } catch (e: any) {
    formError.value = e.message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div v-if="error" class="empty-hint">Failed to load: {{ error }}</div>
  <template v-else>
    <h2>Meetings</h2>
    <div class="toolbar">
      <input v-model="query" placeholder="Search meetings..." />
      <button class="primary" @click="toggleForm">{{ showForm ? "Cancel" : "Add meeting" }}</button>
    </div>

    <div v-if="showForm" class="review-item" style="margin-bottom: 14px">
      <dl class="kv">
        <dt>Title</dt><dd><input v-model="form.title" class="field" placeholder="Meeting title" /></dd>
        <dt>Date</dt><dd><input v-model="form.meet_date" type="date" class="field" /></dd>
        <dt>Participants</dt><dd><input v-model="form.participants" class="field" placeholder="Comma-separated names" /></dd>
        <dt>Transcript</dt>
        <dd><textarea v-model="form.transcript_text" placeholder="Paste the full meeting transcript here..." style="min-height: 140px"></textarea></dd>
      </dl>
      <div v-if="formError" class="empty-hint" style="padding: 6px; color: var(--bad)">{{ formError }}</div>
      <div class="review-actions">
        <button class="primary" :disabled="submitting" @click="submitMeeting">
          {{ submitting ? "Submitting (AI extraction running)..." : "Submit" }}
        </button>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Title</th><th>Date</th><th>Participants</th><th>Deposition</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in meetings.filter(filtered)" :key="m.id" data-meeting @click="openDetail(m.id)">
          <td>{{ m.title }}</td>
          <td>{{ m.meet_date || "-" }}</td>
          <td>{{ (m.participants || []).join(", ") || "-" }}</td>
          <td class="mono">{{ JSON.stringify(m.exp_stat_cache?.type_distribution || {}) }} ({{ m.exp_stat_cache?.total ?? 0 }})</td>
          <td><span class="badge" :class="m.review_status">{{ statusLabel(m.review_status) }}</span></td>
        </tr>
      </tbody>
    </table>
  </template>
</template>
