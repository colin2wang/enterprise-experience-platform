<script setup lang="ts">
defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();
</script>

<template>
  <div v-show="open" class="drawer">
    <div class="drawer-backdrop" @click="emit('close')"></div>
    <aside class="drawer-panel">
      <button class="drawer-close" @click="emit('close')">×</button>
      <slot />
    </aside>
  </div>
</template>
