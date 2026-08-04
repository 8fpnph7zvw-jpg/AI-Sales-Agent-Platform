<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Connection, Key, Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import {
  configureConnector,
  getFeishuConfigStatus,
  getConnectors,
  getWhatsAppConfigStatus,
  testFeishuConnector,
  testWhatsAppConnector,
} from "@/api/connectors";
import { getUsers } from "@/api/users";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import WhatsAppWebConnectPanel from "@/components/connectors/WhatsAppWebConnectPanel.vue";
import type { Connector, SalesUser } from "@/types/business";
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
const testingConnectorId = ref("");
const ownerSaving = ref(false);
const error = ref("");
const rows = ref<Connector[]>([]);
const selected = ref<Connector | null>(null);
const dialogVisible = ref(false);
const configuredKeys = ref<string[]>([]);
const webhookUrl = ref("");
const defaultOwnerId = ref<string | null>(null);
const salesUsers = ref<SalesUser[]>([]);
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
const feishuForm = reactive({
  app_id: "",
  app_secret: "",
});
const isWhatsApp = computed(() => selected.value?.provider === "whatsapp");
const isFeishu = computed(() => selected.value?.provider === "feishu");
const isWhatsAppWeb = computed(
  () => isWhatsApp.value && whatsappForm.adapter === "webjs_gateway",
);
const capabilityLabels: Record<string, string> = {
  receive_messages: "消息接收",
  send_messages: "消息发送",
  delivery_receipts: "状态通知",
  webhooks: "Webhook",
  notifications: "通知",
  messages: "消息",
};
const statusLabels: Record<string, string> = {
  active: "已启用",
  draft: "待测试",
  error: "连接异常",
  inactive: "未启用",
  disabled: "已停用",
};
const healthLabels: Record<string, string> = {
  healthy: "连接正常",
  unhealthy: "连接异常",
  unknown: "待检测",
};

function capabilityLabel(value: string): string {
  return capabilityLabels[value] || "扩展能力";
}

function providerLabel(value: string): string {
  if (value === "whatsapp") return "WhatsApp 商务渠道";
  if (value === "feishu") return "飞书企业通知渠道";
  return "企业消息渠道";
}

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
  defaultOwnerId.value = null;
  Object.assign(whatsappForm, {
    adapter: "cloud_api",
    phone_number_id: row.external_account_id === "demo-template"
      ? ""
      : row.external_account_id,
    access_token: "",
    verify_token: "",
    app_secret: "",
  });
  Object.assign(feishuForm, { app_id: "", app_secret: "" });
  genericConfigRows.splice(
    0,
    genericConfigRows.length,
    { key: "", value: "", value_type: "string", is_secret: true },
  );
  dialogVisible.value = true;
  if (row.provider !== "whatsapp" && row.provider !== "feishu") return;
  statusLoading.value = true;
  try {
    const status = row.provider === "feishu"
      ? await getFeishuConfigStatus(row.id)
      : await getWhatsAppConfigStatus(row.id);
    configuredKeys.value = status.configured_keys;
    if (row.provider === "whatsapp" && "webhook_url" in status) {
      webhookUrl.value = status.webhook_url;
      whatsappForm.adapter = status.adapter === "webjs_gateway" ? "webjs_gateway" : "cloud_api";
      defaultOwnerId.value = status.default_owner_id;
    }
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    statusLoading.value = false;
  }
}

function selectWhatsAppAdapter(value: string): void {
  whatsappForm.adapter = value;
}

function isConfigured(key: string): boolean {
  return configuredKeys.value.includes(key);
}

function configuredPlaceholder(key: string, fallback: string): string {
  return isConfigured(key) ? "已配置，留空保持原值" : fallback;
}

async function save(): Promise<void> {
  if (!selected.value) return;
  if (isWhatsAppWeb.value) return;
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
        default_owner_id: defaultOwnerId.value,
      });
      configuredKeys.value = Array.from(
        new Set([...configuredKeys.value, ...result.configured_keys]),
      );
      ElMessage.success("WhatsApp Cloud API 配置已保存，请执行连接测试");
    } else if (isFeishu.value) {
      const values = Object.entries(feishuForm)
        .filter(([, value]) => value.trim())
        .map(([key, value]) => ({
          key,
          value: value.trim(),
          value_type: "string",
          is_secret: key === "app_secret",
        }));
      const missing = ["app_id", "app_secret"].filter(
        (key) => !isConfigured(key) && !values.some((item) => item.key === key),
      );
      if (missing.length) {
        ElMessage.warning("请填写完整的飞书 App ID 和 App Secret");
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
      Object.assign(feishuForm, { app_id: "", app_secret: "" });
      ElMessage.success("飞书企业应用配置已加密保存，请发送测试通知");
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

async function saveDefaultOwner(): Promise<void> {
  if (!selected.value || !isWhatsApp.value) return;
  ownerSaving.value = true;
  try {
    await configureConnector({
      connector_id: selected.value.id,
      values: [],
      default_owner_id: defaultOwnerId.value,
    });
    ElMessage.success("WhatsApp 默认负责人已保存");
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    ownerSaving.value = false;
  }
}

async function testConnection(): Promise<void> {
  if (!selected.value) return;
  testing.value = true;
  try {
    if (isFeishu.value) {
      const result = await testFeishuConnector();
      ElMessage.success(result.message);
    } else {
      const result = await testWhatsAppConnector(selected.value.id);
      ElMessage.success(
        `${result.message}${result.latency_ms === null ? "" : `（${result.latency_ms} ms）`}`,
      );
    }
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
    await load();
  } finally {
    testing.value = false;
  }
}

async function testFeishuFromCard(connector: Connector): Promise<void> {
  testingConnectorId.value = connector.id;
  try {
    const result = await testFeishuConnector();
    ElMessage.success(result.message);
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    testingConnectorId.value = "";
    await load();
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    getUsers().then((result) => {
      salesUsers.value = result.data.filter(
        (user) => user.role === "sales" && user.status === "active",
      );
    }),
  ]);
});
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
              {{ statusLabels[connector.status] || "待配置" }}
            </el-tag>
          </div>
          <h3>{{ connector.name }}</h3>
          <p>{{ providerLabel(connector.provider) }}</p>
          <div class="connector-capabilities">
            <el-tag
              v-for="capability in connector.capabilities"
              :key="capability"
              size="small"
              effect="plain"
            >
              {{ capabilityLabel(capability) }}
            </el-tag>
          </div>
          <div class="connector-health">
            <span>
              <i :class="{ healthy: connector.health_status === 'healthy' }" />
              {{ healthLabels[connector.health_status || "unknown"] || "待检测" }}
            </span>
            <small>{{ formatDateTime(connector.last_health_check_at) }}</small>
          </div>
          <div class="connector-actions">
            <el-button
              v-permission="['connector.manage', 'connector.secret_manage']"
              :icon="Key"
              @click="openConfig(connector)"
            >
              配置连接
            </el-button>
            <el-button
              v-if="connector.provider === 'feishu'"
              v-permission="['connector.manage', 'connector.secret_manage']"
              :icon="Connection"
              :loading="testingConnectorId === connector.id"
              @click="testFeishuFromCard(connector)"
            >
              测试通知
            </el-button>
          </div>
        </el-card>
      </section>
    </ApiState>

    <el-dialog
      v-model="dialogVisible"
      :title="`配置 ${selected?.name || 'Connector'}`"
      :width="isWhatsAppWeb ? '760px' : '680px'"
      destroy-on-close
    >
      <el-alert
        v-if="isWhatsApp"
        :title="isWhatsAppWeb
          ? 'WhatsApp Web 登录由 Gateway 的 LocalAuth 安全保存，本页面不会读取登录数据。'
          : 'WhatsApp Cloud API 凭据将加密保存，平台不会在页面中展示敏感信息。'"
        type="info"
        show-icon
        :closable="false"
      />
      <el-alert
        v-else-if="isFeishu"
        title="一个企业仅配置一个飞书 App。App Secret 将加密保存，用户通过飞书 OAuth 完成账号绑定。"
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
        <el-form-item label="连接方式" required>
          <el-radio-group
            :model-value="whatsappForm.adapter"
            class="full-width"
            @update:model-value="selectWhatsAppAdapter"
          >
            <el-radio-button value="cloud_api">WhatsApp Cloud API</el-radio-button>
            <el-radio-button value="webjs_gateway">WhatsApp Web 扫码登录</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="默认销售负责人">
          <el-select
            v-model="defaultOwnerId"
            clearable
            class="full-width"
            placeholder="未配置时仅自动分配唯一销售"
          >
            <el-option
              v-for="user in salesUsers"
              :key="user.id"
              :label="user.sales_name || user.display_name"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <template v-if="!isWhatsAppWeb">
          <el-form-item label="商务号码 ID" required>
            <el-input
              v-model="whatsappForm.phone_number_id"
              :placeholder="configuredPlaceholder('phone_number_id', 'Meta Phone Number ID')"
            />
          </el-form-item>
          <el-form-item label="访问凭据" required>
            <el-input
              v-model="whatsappForm.access_token"
              type="password"
              show-password
              :placeholder="configuredPlaceholder('access_token', '永久访问令牌')"
            />
          </el-form-item>
          <el-form-item label="验证凭据" required>
            <el-input
              v-model="whatsappForm.verify_token"
              type="password"
              show-password
              :placeholder="configuredPlaceholder('verify_token', 'Webhook Verify Token')"
            />
          </el-form-item>
          <el-form-item label="应用密钥" required>
            <el-input
              v-model="whatsappForm.app_secret"
              type="password"
              show-password
              :placeholder="configuredPlaceholder('app_secret', 'Meta App Secret')"
            />
          </el-form-item>
          <el-form-item label="Webhook 地址">
            <el-input :model-value="webhookUrl" readonly />
          </el-form-item>
        </template>
        <WhatsAppWebConnectPanel
          v-else
          :connector-id="selected!.id"
          :initial-session-id="selected!.session_id || selected!.id"
          @connected="load"
        />
      </el-form>

      <el-form
        v-else-if="isFeishu"
        v-loading="statusLoading"
        :model="feishuForm"
        label-position="top"
        class="connector-config-form"
      >
        <el-form-item label="飞书 App ID" required>
          <el-input
            v-model="feishuForm.app_id"
            :placeholder="configuredPlaceholder('app_id', 'cli_xxxxxxxxxxxxxxxx')"
          />
        </el-form-item>
        <el-form-item label="飞书 App Secret" required>
          <el-input
            v-model="feishuForm.app_secret"
            type="password"
            show-password
            :placeholder="configuredPlaceholder('app_secret', '企业自建应用 App Secret')"
          />
        </el-form-item>
        <el-alert
          title="测试通知会发送给当前登录管理员；若未绑定，请先在用户管理中完成飞书 OAuth 授权。"
          type="warning"
          show-icon
          :closable="false"
        />
      </el-form>

      <div v-else>
        <div
          v-for="(item, index) in genericConfigRows"
          :key="index"
          class="config-row"
        >
          <el-input v-model="item.key" placeholder="配置项名称" />
          <el-input
            v-model="item.value"
            :type="item.is_secret ? 'password' : 'text'"
            placeholder="配置项内容"
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
          v-if="(isWhatsApp && !isWhatsAppWeb) || isFeishu"
          :icon="Connection"
          :loading="testing"
          @click="testConnection"
        >
          {{ isFeishu ? "测试通知" : "测试连接" }}
        </el-button>
        <el-button
          v-if="isWhatsAppWeb"
          type="primary"
          :loading="ownerSaving"
          @click="saveDefaultOwner"
        >
          保存默认负责人
        </el-button>
        <el-button v-if="!isWhatsAppWeb" type="primary" :loading="saving" @click="save">
          加密保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
