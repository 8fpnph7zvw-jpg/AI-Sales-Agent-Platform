import "vue-router";

export {};

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    icon?: string;
    requiresAuth?: boolean;
    permissions?: string[];
    hideInMenu?: boolean;
  }
}
