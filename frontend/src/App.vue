<script setup lang="ts">
/* EEP shell: topbar, navigation, project switch and detail drawer.
   Author: Wang, Bing <colin2wang@gmail.com> */

import { ref } from "vue";
import { projectId, setProjectId } from "./api";
import { drawerOpen, drawerContent, drawerProps, drawerKey, closeDrawer } from "./drawer";
import Drawer from "./components/Drawer.vue";
import OverviewView from "./views/OverviewView.vue";
import MeetingsView from "./views/MeetingsView.vue";
import ReviewView from "./views/ReviewView.vue";
import ExpListView from "./views/ExpListView.vue";
import ChainView from "./views/ChainView.vue";
import ServicesView from "./views/ServicesView.vue";

const NAV = [
  { name: "overview", label: "Decision Overview", component: OverviewView, props: {} },
  { name: "meetings", label: "Meetings", component: MeetingsView, props: {} },
  { name: "review", label: "Extraction Review", component: ReviewView, props: {} },
  { name: "library", label: "Experience Library", component: ExpListView, props: { kind: "library" } },
  { name: "chain", label: "Evolution Chain", component: ChainView, props: {} },
  { name: "actions", label: "Action Follow-up", component: ExpListView, props: { kind: "actions" } },
  { name: "services", label: "Services", component: ServicesView, props: {} },
];

const active = ref("overview");
// Bumped when the project changes so the active view re-mounts and refetches.
const viewKey = ref(0);

function show(name: string) {
  active.value = name;
}

function onProjectChange(e: Event) {
  setProjectId((e.target as HTMLInputElement).value);
  viewKey.value += 1;
}
</script>

<template>
  <header class="topbar">
    <div class="brand">EEP <span>Enterprise Experience</span></div>
    <nav id="nav">
      <button
        v-for="item in NAV"
        :key="item.name"
        :class="{ active: active === item.name }"
        @click="show(item.name)"
      >
        {{ item.label }}
      </button>
    </nav>
    <label class="project-switch">
      Project
      <input :value="projectId" spellcheck="false" @change="onProjectChange" />
    </label>
  </header>

  <main id="app">
    <section
      v-for="item in NAV"
      :key="item.name"
      :id="`view-${item.name}`"
      class="view"
      :hidden="active !== item.name"
    >
      <component
        v-if="active === item.name"
        :is="item.component"
        v-bind="item.props"
        :key="viewKey"
      />
    </section>
  </main>

  <Drawer :open="drawerOpen" @close="closeDrawer">
    <div v-if="drawerOpen && drawerContent" :key="drawerKey">
      <component :is="drawerContent" v-bind="drawerProps" />
    </div>
  </Drawer>
</template>
