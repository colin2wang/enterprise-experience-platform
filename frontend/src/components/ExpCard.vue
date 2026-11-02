<script setup lang="ts">
import { statusLabel, typeLabel } from "../labels";
import type { Experience } from "../types";

defineProps<{ exp: Experience }>();
defineEmits<{ (e: "open", id: string): void }>();
</script>

<template>
  <div class="card" data-exp :data-exp-id="exp.id" @click="$emit('open', exp.id)">
    <span class="code">{{ exp.code || exp.id.slice(0, 8) }}</span>
    <span class="badge" :class="exp.status">{{ statusLabel(exp.status) }}</span>
    <div class="title">{{ exp.title }}</div>
    <div class="meta">
      {{ typeLabel(exp.type) }}<template v-if="exp.due_date"> · due {{ exp.due_date }}</template>
    </div>
  </div>
</template>
