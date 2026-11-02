/* Shared drawer store: any view can open the detail drawer with a component. */

import { shallowRef, ref, type Component } from "vue";

export const drawerOpen = ref(false);
export const drawerContent = shallowRef<Component | null>(null);
export const drawerProps = shallowRef<Record<string, unknown>>({});
// Bumped on each open so detail components re-mount and refetch.
export const drawerKey = ref(0);

export function openDrawer(content: Component, props: Record<string, unknown> = {}) {
  drawerContent.value = content;
  drawerProps.value = props;
  drawerKey.value += 1;
  drawerOpen.value = true;
}

export function closeDrawer() {
  drawerOpen.value = false;
}
