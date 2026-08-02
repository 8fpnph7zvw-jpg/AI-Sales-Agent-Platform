<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowDown,
  ChatDotRound,
  Connection,
  DataAnalysis,
  Document,
  Files,
  Fold,
  MagicStick,
  Menu as MenuIcon,
  Operation,
  OfficeBuilding,
  Setting,
  SwitchButton,
  User,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { useAuthStore } from "@/stores/auth";

interface MenuItem {
  path: string;
  label: string;
  icon: Component;
  permissions: string[];
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const collapsed = ref(false);
const mobileOpen = ref(false);

const menuItems: MenuItem[] = [
  { path: "/dashboard", label: "Dashboard", icon: DataAnalysis, permissions: ["dashboard.read"] },
  {
    path: "/customers",
    label: auth.canAny(["customer.read_all"]) ? "客户管理" : "我的客户",
    icon: User,
    permissions: ["customer.read_own", "customer.read_team", "customer.read_all"],
  },
  { path: "/agent", label: "AI客服", icon: MagicStick, permissions: ["ai_agent.chat"] },
  {
    path: "/conversations",
    label: auth.canAny(["conversation.read_all"]) ? "聊天记录" : "我的聊天记录",
    icon: ChatDotRound,
    permissions: [
      "conversation.read_own",
      "conversation.read_team",
      "conversation.read_all",
    ],
  },
  {
    path: "/lead-score",
    label: "客户评分结果",
    icon: Operation,
    permissions: ["customer.score_read", "customer.score"],
  },
  { path: "/knowledge", label: "知识库", icon: Files, permissions: ["knowledge.read"] },
  {
    path: "/quotations",
    label: auth.canAny(["quotation.read_all"]) ? "报价管理" : "我的报价",
    icon: Document,
    permissions: ["quotation.read_own", "quotation.read_all", "quotation.create"],
  },
  { path: "/connectors", label: "Connector管理", icon: Connection, permissions: ["connector.read"] },
  { path: "/workflows", label: "Workflow管理", icon: MenuIcon, permissions: ["workflow.read"] },
  { path: "/users", label: "用户管理", icon: User, permissions: ["user.read"] },
  {
    path: "/system",
    label: "系统设置",
    icon: Setting,
    permissions: ["system_config.read", "role.read", "user.read", "audit.read"],
  },
];

const visibleMenuItems = computed(() =>
  menuItems.filter((item) => auth.canAny(item.permissions)),
);
const pageTitle = computed(() => String(route.meta.title || "AI Sales Agent"));
const initials = computed(() => auth.user?.display_name.trim().slice(0, 1).toUpperCase() || "U");

function navigate(path: string): void {
  mobileOpen.value = false;
  void router.push(path);
}

function logout(): void {
  auth.logout();
  void router.replace("/login");
}

function backToLogin(): void {
  auth.logout();
  void router.replace("/login");
}

function handleExpired(): void {
  auth.logout();
  ElMessage.warning("登录状态已过期，请重新登录");
  void router.replace({ name: "login", query: { redirect: route.fullPath } });
}

onMounted(() => window.addEventListener("auth:expired", handleExpired));
onBeforeUnmount(() => window.removeEventListener("auth:expired", handleExpired));
</script>

<template>
  <div class="admin-shell" :class="{ 'admin-shell--collapsed': collapsed }">
    <div v-if="mobileOpen" class="mobile-overlay" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar--mobile-open': mobileOpen }">
      <button class="brand" type="button" @click="navigate('/dashboard')">
        <span class="brand__mark">AI</span>
        <span v-if="!collapsed" class="brand__copy">
          <strong>Sales Agent</strong>
          <small>Enterprise Console</small>
        </span>
      </button>

      <div v-if="!collapsed" class="menu-caption">工作台</div>
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :collapse-transition="false"
        class="sidebar-menu"
        @select="navigate"
      >
        <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar__footer">
        <button class="collapse-button" type="button" @click="collapsed = !collapsed">
          <el-icon><Fold /></el-icon>
          <span v-if="!collapsed">收起导航</span>
        </button>
      </div>
    </aside>

    <div class="admin-main">
      <header class="topbar">
        <div class="topbar__left">
          <button class="mobile-menu-button" type="button" @click="mobileOpen = true">
            <el-icon><MenuIcon /></el-icon>
          </button>
          <div>
            <small>AI Sales Agent Platform</small>
            <strong>{{ pageTitle }}</strong>
          </div>
        </div>
        <div class="tenant-chip">
          <el-icon><OfficeBuilding /></el-icon>
          <span>{{ auth.user?.tenant_id }}</span>
        </div>
        <el-dropdown trigger="click">
          <button class="user-menu" type="button">
            <span class="user-avatar">{{ initials }}</span>
            <span class="user-copy">
              <strong>{{ auth.user?.display_name }}</strong>
              <small>{{ auth.user?.email }}</small>
            </span>
            <el-icon><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ auth.user?.tenant_id }}</el-dropdown-item>
              <el-dropdown-item divided @click="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button class="topbar-login-button" plain @click="backToLogin">
          <el-icon><SwitchButton /></el-icon>
          返回登录
        </el-button>
        <el-button type="danger" plain @click="logout">退出登录</el-button>
      </header>

      <main class="page-container">
        <router-view />
      </main>
    </div>
  </div>
</template>
