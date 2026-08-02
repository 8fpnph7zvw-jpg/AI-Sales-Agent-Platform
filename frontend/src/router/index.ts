import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
    meta: { title: "登录" },
  },
  {
    path: "/",
    component: () => import("@/layouts/AdminLayout.vue"),
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "/dashboard",
      },
      {
        path: "dashboard",
        name: "dashboard",
        component: () => import("@/views/dashboard/DashboardView.vue"),
        meta: { title: "Dashboard", permissions: ["dashboard.read"] },
      },
      {
        path: "customers",
        name: "customers",
        component: () => import("@/views/customers/CustomerListView.vue"),
        meta: {
          title: "客户管理",
          permissions: ["customer.read_own", "customer.read_team", "customer.read_all"],
        },
      },
      {
        path: "agent",
        name: "agent",
        component: () => import("@/views/agent/AgentConsoleView.vue"),
        meta: { title: "AI客服", permissions: ["ai_agent.chat"] },
      },
      {
        path: "conversations",
        name: "conversations",
        component: () => import("@/views/conversations/ConversationListView.vue"),
        meta: {
          title: "聊天记录",
          permissions: [
            "conversation.read_own",
            "conversation.read_team",
            "conversation.read_all",
          ],
        },
      },
      {
        path: "lead-score",
        name: "lead-score",
        component: () => import("@/views/lead-score/LeadScoreView.vue"),
        meta: { title: "客户评分", permissions: ["customer.score_read", "customer.score"] },
      },
      {
        path: "knowledge",
        name: "knowledge",
        component: () => import("@/views/knowledge/KnowledgeView.vue"),
        meta: { title: "知识库", permissions: ["knowledge.read"] },
      },
      {
        path: "quotations",
        name: "quotations",
        component: () => import("@/views/quotations/QuotationView.vue"),
        meta: {
          title: "报价管理",
          permissions: ["quotation.read_own", "quotation.read_all", "quotation.create"],
        },
      },
      {
        path: "connectors",
        name: "connectors",
        component: () => import("@/views/connectors/ConnectorView.vue"),
        meta: { title: "Connector管理", permissions: ["connector.read"] },
      },
      {
        path: "connectors/whatsapp",
        name: "whatsapp-connector",
        redirect: "/connectors",
        meta: { requiresAuth: true, hideInMenu: true },
      },
      {
        path: "workflows",
        name: "workflows",
        component: () => import("@/views/workflows/WorkflowView.vue"),
        meta: { title: "Workflow管理", permissions: ["workflow.read"] },
      },
      {
        path: "users",
        name: "users",
        component: () => import("@/views/users/UserManagementView.vue"),
        meta: { title: "用户管理", permissions: ["user.read"] },
      },
      {
        path: "system",
        name: "system",
        component: () => import("@/views/system/SystemSettingsView.vue"),
        meta: {
          title: "系统设置",
          permissions: ["system_config.read", "role.read", "user.read", "audit.read"],
        },
      },
      {
        path: "403",
        name: "forbidden",
        component: () => import("@/views/errors/ForbiddenView.vue"),
        meta: { title: "无访问权限", hideInMenu: true },
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/dashboard",
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && auth.isAuthenticated) {
    try {
      await auth.restoreSession();
    } catch {
      // Authentication failures clear the session; transient network failures
      // keep the cached route available and retry on the next navigation.
    }
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "dashboard" };
  }
  if (to.meta.permissions?.length && !auth.canAny(to.meta.permissions)) {
    return { name: "forbidden" };
  }

  document.title = to.meta.title
    ? `${to.meta.title} · AI Sales Agent`
    : "AI Sales Agent Platform";
  return true;
});
