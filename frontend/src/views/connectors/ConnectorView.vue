<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Key, Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { configureConnector, getConnectors } from "@/api/connectors";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { Connector } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const rows = ref<Connector[]>([]);
const selected = ref<Connector | null>(null);
const dialogVisible = ref(false);
const configRows = reactive([{ key: "", value: "", value_type: "string", is_secret: true }]);

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

function openConfig(row: Connector): void {
  selected.value = row;
  configRows.splice(0, configRows.length, { key: "", value: "", value_type: "string", is_secret: true });
  dialogVisible.value = true;
}

async function save(): Promise<void> {
  if (!selected.value || configRows.some((item) => !item.key)) {
    ElMessage.warning("请填写配置键");
    return;
  }
  saving.value = true;
  try {
    const result = await configureConnector({
      connector_id: selected.value.id,
      values: configRows.map((item) => ({ ...item })),
    });
    ElMessage.success(`已安全保存 ${result.configured_keys.length} 个配置项`);
    dialogVisible.value = false;
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="Connector管理" description="管理外部渠道连接状态和加密凭据">
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新状态</el-button>
    </PageHeader>
    <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无 Connector" @retry="load">
      <section class="connector-grid">
        <el-card v-for="connector in rows" :key="connector.id" shadow="hover" class="connector-card">
          <div class="connector-card__top">
            <span class="connector-logo">{{ connector.provider.slice(0, 2).toUpperCase() }}</span>
            <el-tag :type="connector.status === 'active' ? 'success' : 'info'">{{ connector.status }}</el-tag>
          </div>
          <h3>{{ connector.name }}</h3>
          <p>{{ connector.provider }} · {{ connector.external_account_id }}</p>
          <div class="connector-capabilities">
            <el-tag v-for="capability in connector.capabilities" :key="capability" size="small" effect="plain">{{ capability }}</el-tag>
          </div>
          <div class="connector-health">
            <span><i :class="{ healthy: connector.health_status === 'healthy' }" />{{ connector.health_status || "未检查" }}</span>
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

    <el-dialog v-model="dialogVisible" :title="`配置 ${selected?.name || 'Connector'}`" width="680px">
      <el-alert title="配置值将由后端加密保存，前端不会读取已保存的明文密钥。" type="info" show-icon :closable="false" />
      <div v-for="(item, index) in configRows" :key="index" class="config-row">
        <el-input v-model="item.key" placeholder="配置键，例如 api_key" />
        <el-input v-model="item.value" :type="item.is_secret ? 'password' : 'text'" show-password placeholder="配置值" />
        <el-checkbox v-model="item.is_secret">敏感</el-checkbox>
        <el-button text type="danger" @click="configRows.splice(index, 1)">删除</el-button>
      </div>
      <el-button text type="primary" @click="configRows.push({ key: '', value: '', value_type: 'string', is_secret: true })">+ 添加配置项</el-button>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">加密保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
