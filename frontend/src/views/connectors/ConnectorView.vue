<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Connection, Key, Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import {
  configureConnector,
  getConnectors,
  getWhatsAppConfigStatus,
  testWhatsAppConnector,
} from "@/api/connectors";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { Connector } from "@/types/business";
import { formatDateTime } from "@/utils/format";

interface GenericConfigRow {
  key: string;
  value: string;
  value_type: string;
  is_secret: boolean;
}

const loading = ref(false);
const statusLoading = ref(false);
const saving = ref(false);
const testing = ref(false);
const error = ref("");
const rows = ref<Connector[]>([]);
const selected = ref<Connector | null>(null);
const dialogVisible = ref(false);
const configuredKeys = ref<string[]>([]);
const webhookUrl = ref("");
const genericConfigRows = reactive<GenericConfigRow[]>([
  { key: "", value: "", value_type: "string", is_secret: true },
]);
const whatsappForm = reactive({
  adapter: "cloud_api",
  phone_number_id: "",
  access_token: "",
  verify_token: "",
  app_secret: "",
});
const isWhatsApp = computed(() => selected.value?.provider === "whatsapp");

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await getConnectors();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

async function openConfig(row: Connector): Promise<void> {
  selected.value = row;
  configuredKeys.value = [];
  webhookUrl.value = "";
  Object.assign(whatsappForm, {
    adapter: "cloud_api",
    phone_number_id: row.external_account_id === "demo-template"
      ? ""
      : row.external_account_id,
    access_token: "",
    verify_token: "",
    app_secret: "",
  });
  genericConfigRows.splice(
    0,
    genericConfigRows.length,
    { key: "", value: "", value_type: "string", is_secret: true },
  );
  dialogVisible.value = true;
  if (row.provider !== "whatsapp") return;
  statusLoading.value = true;
  try {
    const status = await getWhatsAppConfigStatus(row.id);
    configuredKeys.value = status.configured_keys;
    webhookUrl.value = status.webhook_url;
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    statusLoading.value = false;
  }
}

function isConfigured(key: string): boolean {
  return configuredKeys.value.includes(key);
}

function configuredPlaceholder(key: string, fallback: string): string {
  return isConfigured(key) ? "已配置，留空保持原值" : fallback;
}

async function save(): Promise<void> {
  if (!selected.value) return;
  saving.value = true;
  try {
    if (isWhatsApp.value) {
      const values = Object.entries(whatsappForm)
        .filter(([, value]) => value.trim())
        .map(([key, value]) => ({
          key,
          value: value.trim(),
          value_type: "string",
          is_secret: false,
        }));
      const missing = ["phone_number_id", "access_token", "verify_token", "app_secret"].filter(
        (key) => !isConfigured(key) && !values.some((item) => item.key === key),
      );
      if (missing.length) {
        ElMessage.warning(`请填写完整 WhatsApp 配置：${missing.join(", ")}`);
        return;
      }
      if (!values.length) {
        ElMessage.info("没有需要保存的配置变更");
        return;
      }
      const result = await configureConnector({
        connector_id: selected.value.id,
        values,
      });
      configuredKeys.value = Array.from(
        new Set([...configuredKeys.value, ...result.configured_keys]),
      );
      ElMessage.success("WhatsApp Cloud API 配置已保存，请执行连接测试");
    } else {
      if (genericConfigRows.some((item) => !item.key || !item.value)) {
        ElMessage.warning("请填写配置键和值");
        return;
      }
      const result = await configureConnector({
        connector_id: selected.value.id,
        values: genericConfigRows.map((item) => ({ ...item })),
      });
      ElMessage.success(`已安全保存 ${result.configured_keys.length} 个配置项`);
      dialogVisible.value = false;
    }
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    saving.value = false;
  }
}

async function testConnection(): Promise<void> {
  if (!selected.value) return;
  testing.value = true;
  try {
    const result = await testWhatsAppConnector(selected.value.id);
    ElMessage.success(
      `${result.message}${result.latency_ms === null ? "" : `（${result.latency_ms} ms）`}`,
    );
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
    await load();
  } finally {
    testing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="Connector 管理" description="管理外部渠道连接状态和加密凭据">
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新状态</el-button>
    </PageHeader>
    <ApiState
      :loading="loading"
      :error="error"
      :empty="!rows.length"
      empty-text="暂无 Connector"
      @retry="load"
    >
      <section class="connector-grid">
        <el-card
          v-for="connector in rows"
          :key="connector.id"
          shadow="hover"
          class="connector-card"
        >
          <div class="connector-card__top">
            <span class="connector-logo">
              {{ connector.provider.slice(0, 2).toUpperCase() }}
            </span>
            <el-tag :type="connector.status === 'active' ? 'success' : 'info'">
              {{ connector.status }}
            </el-tag>
          </div>
          <h3>{{ connector.name }}</h3>
          <p>{{ connector.provider }} · {{ connector.external_account_id }}</p>
          <div class="connector-capabilities">
            <el-tag
              v-for="capability in connector.capabilities"
              :key="capability"
              size="small"
              effect="plain"
            >
              {{ capability }}
            </el-tag>
          </div>
          <div class="connector-health">
            <span>
              <i :class="{ healthy: connector.health_status === 'healthy' }" />
              {{ connector.health_status || "未检查" }}
            </span>
            <small>{{ formatDateTime(connector.last_health_check_at) }}</small>
          </div>
          <el-button
            v-permission="['connector.manage', 'connector.secret_manage']"
            :icon="Key"
            @click="openConfig(connector)"
          >
            配置连接
          </el-button>
        </el-card>
      </section>
    </ApiState>

    <el-dialog
      v-model="dialogVisible"
      :title="`配置 ${selected?.name || 'Connector'}`"
      width="680px"
      destroy-on-close
    >
      <el-alert
        title="WhatsApp 使用 provider adapter；Graph API 地址由服务端管理，租户凭据在此加密保存。"
        type="info"
        show-icon
        :closable="false"
      />

      <el-form
        v-if="isWhatsApp"
        v-loading="statusLoading"
        :model="whatsappForm"
        label-position="top"
        class="connector-config-form"
      >
        <el-form-item label="Provider Adapter" required>
          <el-select v-model="whatsappForm.adapter">
            <el-option label="WhatsApp Cloud API" value="cloud_api" />
          </el-select>
        </el-form-item>
        <el-form-item label="Phone Number ID" required>
          <el-input
            v-model="whatsappForm.phone_number_id"
            :placeholder="configuredPlaceholder('phone_number_id', 'Meta Phone Number ID')"
          />
        </el-form-item>
        <el-form-item label="Access Token" required>
          <el-input
            v-model="whatsappForm.access_token"
            type="password"
            show-password
            :placeholder="configuredPlaceholder('access_token', '永久访问令牌')"
          />
        </el-form-item>
        <el-form-item label="Verify Token" required>
          <el-input
            v-model="whatsappForm.verify_token"
            type="password"
            show-password
            :placeholder="configuredPlaceholder('verify_token', 'Webhook Verify Token')"
          />
        </el-form-item>
        <el-form-item label="App Secret" required>
          <el-input
            v-model="whatsappForm.app_secret"
            type="password"
            show-password
            :placeholder="configuredPlaceholder('app_secret', 'Meta App Secret')"
          />
        </el-form-item>
        <el-form-item label="Webhook URL">
          <el-input :model-value="webhookUrl" readonly />
        </el-form-item>
      </el-form>

      <div v-else>
        <div
          v-for="(item, index) in genericConfigRows"
          :key="index"
          class="config-row"
        >
          <el-input v-model="item.key" placeholder="配置键，例如 api_key" />
          <el-input
            v-model="item.value"
            :type="item.is_secret ? 'password' : 'text'"
            placeholder="配置值"
          />
          <el-checkbox v-model="item.is_secret">敏感</el-checkbox>
          <el-button text type="danger" @click="genericConfigRows.splice(index, 1)">
            删除
          </el-button>
        </div>
        <el-button
          text
          type="primary"
          @click="genericConfigRows.push({
            key: '',
            value: '',
            value_type: 'string',
            is_secret: true,
          })"
        >
          + 添加配置项
        </el-button>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          v-if="isWhatsApp"
          :icon="Connection"
          :loading="testing"
          @click="testConnection"
        >
          测试连接
        </el-button>
        <el-button type="primary" :loading="saving" @click="save">
          加密保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
