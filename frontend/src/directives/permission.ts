import type { App, DirectiveBinding } from "vue";

import { useAuthStore } from "@/stores/auth";

function applyPermission(el: HTMLElement, binding: DirectiveBinding<string | string[]>): void {
  const auth = useAuthStore();
  const permissions = Array.isArray(binding.value) ? binding.value : [binding.value];
  if (!auth.canAny(permissions)) {
    el.remove();
  }
}

export function installPermissionDirective(app: App): void {
  app.directive("permission", {
    mounted: applyPermission,
    updated: applyPermission,
  });
}
