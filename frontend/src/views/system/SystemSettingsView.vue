<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { getSystemConfigs, updateSystemConfig } from "@/api/system";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";
import type { SystemConfig } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const auth = useAuthStore();
const loading = ref(false);
const savingKey = ref("");
const error = ref("");
const configs = ref<SystemConfig[]>([]);
const editValues = ref<Record<string, string>>({});

function displayValue(config: SystemConfig): string {
  if (config.is_secret) return "••••••••";
  return typeof config.value === "string" ? config.value : JSON.stringify(config.value);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    configs.value = await getSystemConfigs();
    editValues.value = Object.fromEntries(
      configs.value.map((config) => [config.key, displayValue(config)]),
    );
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

async function save(config: SystemConfig): Promise<void> {
  savingKey.value = config.key;
  try {
    let value: unknown = editValues.value[config.key];
    if (config.value_type === "number") value = Number(value);
    if (config.value_type === "boolean") value = value === "true";
    if (config.value_type === "json") value = JSON.parse(String(value));
    await updateSystemConfig(config.key, value);
    ElMessage.success("系统配置已更新");
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    savingKey.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="系统设置" description="租户配置、账号权限与系统运行参数" />
    <el-card shadow="never" class="content-card account-summary">
      <div class="account-summary__avatar">{{ auth.user?.display_name.slice(0, 1).toUpperCase() }}</div>
      <div><strong>{{ auth.user?.display_name }}</strong><span>{{ auth.user?.email }}</span></div>
      <div><small>租户 ID</small><strong>{{ auth.user?.tenant_id }}</strong></div>
      <div><small>已授予权限</small><strong>{{ auth.user?.permissions.length }}</strong></div>
    </el-card>

    <el-card shadow="never" class="content-card settings-card">
      <template #header>
        <div class="card-heading"><div><strong>租户配置</strong><span>配置项由后端 API 加载并持久化</span></div></div>
      </template>
      <ApiState :loading="loading" :error="error" :empty="!configs.length" empty-text="暂无系统配置" @retry="load">
        <div class="settings-list">
          <div v-for="config in configs" :key="config.key" class="setting-item">
            <div class="setting-item__meta">
              <strong>{{ config.key }}</strong>
              <span>{{ config.value_type }} · 更新于 {{ formatDateTime(config.updated_at) }}</span>
            </div>
            <el-input
              v-model="editValues[config.key]"
              :type="config.is_secret ? 'password' : 'text'"
              :show-password="config.is_secret"
              :disabled="!auth.canAny(['system_config.manage'])"
            />
            <el-button
              v-if="auth.canAny(['system_config.manage'])"
              type="primary"
              plain
              :loading="savingKey === config.key"
              @click="save(config)"
            >
              保存
            </el-button>
          </div>
        </div>
      </ApiState>
    </el-card>
  </div>
</template>
