<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { CircleCheck, Connection, Iphone, Key, Refresh, Warning } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import {
  createOpenWASession,
  getOpenWAQRCode,
  getOpenWAStatus,
  reconnectOpenWA,
  type OpenWAStatus,
} from "@/api/connectors";
import { getApiErrorMessage } from "@/api/client";

const status = ref<OpenWAStatus | null>(null);
const qrDataUrl = ref("");
const loading = ref(false);
let pollTimer: number | undefined;

const statusMeta = computed(() => {
  const value = status.value?.status;
  if (value === "ready") return { label: "已连接", type: "success", icon: CircleCheck } as const;
  if (["qr", "authenticated", "starting", "reconnecting"].includes(value || "")) {
    return { label: value === "qr" ? "等待扫码" : "正在连接", type: "warning", icon: Warning } as const;
  }
  return { label: "未连接", type: "info", icon: Connection } as const;
});

async function refresh(silent = false): Promise<void> {
  if (!silent) loading.value = true;
  try {
    status.value = await getOpenWAStatus();
    if (status.value.status === "ready") qrDataUrl.value = "";
    else if (status.value.qr_available && !qrDataUrl.value) {
      const qr = await getOpenWAQRCode();
      qrDataUrl.value = qr.data_url;
    }
  } catch (error) {
    if (!silent) ElMessage.error(getApiErrorMessage(error));
  } finally {
    if (!silent) loading.value = false;
  }
}

async function createSession(): Promise<void> {
  loading.value = true;
  try {
    status.value = await createOpenWASession();
    ElMessage.success("Session 已创建，正在生成二维码");
    window.setTimeout(() => void refresh(true), 1200);
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    loading.value = false;
  }
}

async function showQRCode(): Promise<void> {
  loading.value = true;
  try {
    const value = await getOpenWAQRCode();
    qrDataUrl.value = value.data_url;
    ElMessage.success("请使用 WhatsApp 扫描二维码");
  } catch (error) {
    ElMessage.warning(getApiErrorMessage(error));
    await refresh(true);
  } finally {
    loading.value = false;
  }
}

async function reconnect(): Promise<void> {
  loading.value = true;
  try {
    status.value = await reconnectOpenWA();
    qrDataUrl.value = "";
    ElMessage.success("已发起重新连接");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refresh();
  pollTimer = window.setInterval(() => void refresh(true), 5000);
});
onUnmounted(() => window.clearInterval(pollTimer));
</script>

<template>
  <div class="whatsapp-page" v-loading="loading">
    <div class="enterprise-page-header">
      <div>
        <span class="eyebrow">CHANNEL OPERATIONS</span>
        <h1>WhatsApp Connector</h1>
        <p>连接企业 WhatsApp，实时接收客户消息并由 AI 销售助手自动响应。</p>
      </div>
      <el-button :icon="Refresh" @click="refresh()">刷新状态</el-button>
    </div>

    <div class="connector-grid">
      <el-card class="status-card" shadow="never">
        <div class="status-card__hero">
          <span class="whatsapp-mark"><Iphone /></span>
          <div><small>OPENWA SERVICE</small><h2>连接状态</h2></div>
          <el-tag :type="statusMeta.type" size="large" effect="light">
            <el-icon><component :is="statusMeta.icon" /></el-icon> {{ statusMeta.label }}
          </el-tag>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="Session ID">{{ status?.session_id || "尚未创建" }}</el-descriptions-item>
          <el-descriptions-item label="API Key">
            <el-tag :type="status?.api_key_configured ? 'success' : 'danger'">
              <el-icon><Key /></el-icon> {{ status?.api_key_configured ? "已安全配置" : "未配置" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="WhatsApp 账号">{{ status?.phone_number || "等待连接" }}</el-descriptions-item>
        </el-descriptions>
        <div class="connector-actions">
          <el-button type="primary" @click="createSession">创建 Session</el-button>
          <el-button type="success" :disabled="!status?.session_id" @click="showQRCode">连接 WhatsApp</el-button>
          <el-button :disabled="!status?.session_id" @click="reconnect">重新连接</el-button>
        </div>
      </el-card>

      <el-card class="qr-card" shadow="never">
        <template #header><strong>手机扫码登录</strong></template>
        <div v-if="qrDataUrl" class="qr-stage">
          <img :src="qrDataUrl" alt="WhatsApp 登录二维码" />
          <p>二维码会定期刷新，请尽快完成扫描</p>
        </div>
        <div v-else class="qr-empty">
          <el-icon><Iphone /></el-icon>
          <h3>等待生成二维码</h3>
          <p>点击“连接 WhatsApp”，二维码将在此处安全显示。</p>
        </div>
        <ol class="scan-guide">
          <li>打开手机 WhatsApp</li><li>进入“设置 → 已关联设备”</li><li>点击“关联设备”并扫描上方二维码</li>
        </ol>
      </el-card>
    </div>
  </div>
</template>
