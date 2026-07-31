<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  CircleCheck,
  Connection,
  Iphone,
  Loading,
  RefreshRight,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import {
  connectWhatsAppWeb,
  getWhatsAppWebErrorMessage,
  getWhatsAppWebQr,
  getWhatsAppWebStatus,
  type WhatsAppWebStatus,
} from "@/api/whatsapp-web";

const props = withDefaults(defineProps<{ initialSessionId?: string }>(), {
  initialSessionId: "customer001",
});

const STORAGE_KEY = "ai-sales:whatsapp-web:session-id";
const sessionId = ref(localStorage.getItem(STORAGE_KEY) || props.initialSessionId);
const status = ref<WhatsAppWebStatus>("DISCONNECTED");
const phone = ref<string | null>(null);
const qrDataUrl = ref<string | null>(null);
const errorMessage = ref("");
const connecting = ref(false);
const refreshing = ref(false);
let pollTimer: number | undefined;

const statusPresentation = computed(() => {
  if (status.value === "CONNECTED") {
    return { label: "已连接", type: "success" as const, icon: CircleCheck };
  }
  if (status.value === "WAITING_QR") {
    return { label: "等待扫码", type: "warning" as const, icon: Iphone };
  }
  if (status.value === "CONNECTING") {
    return { label: "连接中", type: "primary" as const, icon: Loading };
  }
  return { label: "断开", type: "info" as const, icon: Warning };
});

const validSessionId = computed(() => /^[A-Za-z0-9_-]{1,64}$/.test(sessionId.value));

function applyStatus(next: {
  status: WhatsAppWebStatus;
  phone: string | null;
  lastError: string | null;
}): void {
  status.value = next.status;
  phone.value = next.phone;
  errorMessage.value = next.lastError || "";
  if (next.status === "CONNECTED") qrDataUrl.value = null;
}

async function refreshQr(): Promise<void> {
  if (status.value !== "WAITING_QR") return;
  const result = await getWhatsAppWebQr(sessionId.value);
  qrDataUrl.value = result.dataUrl;
}

async function refreshStatus(options: { silent?: boolean } = {}): Promise<void> {
  if (!validSessionId.value || refreshing.value) return;
  refreshing.value = true;
  try {
    const result = await getWhatsAppWebStatus(sessionId.value);
    applyStatus(result);
    await refreshQr();
  } catch (error) {
    if (!options.silent) errorMessage.value = getWhatsAppWebErrorMessage(error);
  } finally {
    refreshing.value = false;
  }
}

function startPolling(): void {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = window.setInterval(() => refreshStatus({ silent: true }), 2_500);
}

async function connect(): Promise<void> {
  if (!validSessionId.value) {
    ElMessage.warning("sessionId 仅支持字母、数字、下划线和连字符，最长 64 位");
    return;
  }
  connecting.value = true;
  errorMessage.value = "";
  qrDataUrl.value = null;
  localStorage.setItem(STORAGE_KEY, sessionId.value);
  try {
    applyStatus(await connectWhatsAppWeb(sessionId.value));
    startPolling();
    await refreshStatus();
  } catch (error) {
    errorMessage.value = getWhatsAppWebErrorMessage(error);
    ElMessage.error(errorMessage.value);
  } finally {
    connecting.value = false;
  }
}

onMounted(() => {
  refreshStatus({ silent: true });
  startPolling();
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <section class="web-connect-panel">
    <div class="web-connect-panel__header">
      <div>
        <span class="web-connect-panel__eyebrow">LOCAL AUTH SESSION</span>
        <h3>WhatsApp Web 扫码连接</h3>
        <p>扫码后登录信息会由 Gateway 持久化，服务重启无需重复绑定。</p>
      </div>
      <el-tag :type="statusPresentation.type" effect="light" round>
        <el-icon :class="{ 'is-loading': status === 'CONNECTING' }">
          <component :is="statusPresentation.icon" />
        </el-icon>
        {{ statusPresentation.label }}
      </el-tag>
    </div>

    <div class="web-session-row">
      <el-input
        v-model.trim="sessionId"
        :disabled="connecting"
        maxlength="64"
        placeholder="例如 customer001"
        @keyup.enter="connect"
      >
        <template #prepend>sessionId</template>
      </el-input>
      <el-button
        type="primary"
        :icon="Connection"
        :loading="connecting"
        @click="connect"
      >
        {{ status === "CONNECTED" ? "重新连接" : "连接" }}
      </el-button>
    </div>

    <div class="web-connection-stage">
      <div v-if="status === 'CONNECTED'" class="web-connected-state">
        <span class="web-connected-state__icon"><CircleCheck /></span>
        <h4>WhatsApp 已连接</h4>
        <p v-if="phone">当前账号：+{{ phone }}</p>
        <p>AI 自动回复链路已准备就绪。</p>
      </div>

      <div v-else-if="qrDataUrl" class="web-qr-state">
        <div class="web-qr-frame">
          <img :src="qrDataUrl" alt="WhatsApp Web 登录二维码" />
        </div>
        <h4>使用手机 WhatsApp 扫码</h4>
        <p>设置 → 已关联的设备 → 关联设备</p>
      </div>

      <div v-else class="web-waiting-state">
        <el-icon :class="{ 'is-loading': status === 'CONNECTING' || refreshing }">
          <Loading v-if="status === 'CONNECTING' || refreshing" />
          <Iphone v-else />
        </el-icon>
        <h4>{{ status === "WAITING_QR" ? "正在生成二维码" : "尚未建立连接" }}</h4>
        <p>
          {{ status === "WAITING_QR" ? "二维码生成后会自动显示" : "输入 sessionId 后点击连接" }}
        </p>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="web-connect-panel__footer">
      <span>状态每 2.5 秒自动更新</span>
      <el-button text type="primary" :icon="RefreshRight" @click="refreshStatus()">
        立即刷新
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.web-connect-panel { display: grid; gap: 18px; margin-top: 18px; }
.web-connect-panel__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 18px; border: 1px solid #e2e9f2; border-radius: 14px; background: linear-gradient(135deg, #f8fbff, #f4fbf8); }
.web-connect-panel__header h3 { margin: 5px 0; color: #172033; font-size: 18px; }
.web-connect-panel__header p { margin: 0; color: #738096; font-size: 12px; line-height: 1.6; }
.web-connect-panel__header .el-tag { display: inline-flex; align-items: center; gap: 5px; flex: 0 0 auto; }
.web-connect-panel__eyebrow { color: #17956a; font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.web-session-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
.web-session-row .el-button { min-width: 106px; }
.web-connection-stage { min-height: 310px; display: grid; place-items: center; padding: 24px; overflow: hidden; border: 1px solid #dfe7f0; border-radius: 16px; background: radial-gradient(circle at 50% 20%, rgba(37, 211, 102, .08), transparent 35%), #f8fafc; }
.web-connected-state,.web-qr-state,.web-waiting-state { display: grid; justify-items: center; text-align: center; }
.web-connected-state__icon { width: 72px; height: 72px; display: grid; place-items: center; border-radius: 22px; color: #fff; background: linear-gradient(135deg, #25d366, #0ca678); box-shadow: 0 16px 34px rgba(20, 170, 105, .23); }
.web-connected-state__icon svg { width: 38px; }
.web-connection-stage h4 { margin: 17px 0 6px; color: #1d2939; font-size: 17px; }
.web-connection-stage p { margin: 2px 0; color: #7b879a; font-size: 12px; }
.web-qr-frame { padding: 13px; border: 1px solid #d9e2ed; border-radius: 18px; background: #fff; box-shadow: 0 18px 40px rgba(29, 48, 82, .09); }
.web-qr-frame img { display: block; width: 230px; height: 230px; }
.web-waiting-state > .el-icon { color: #8b99ad; font-size: 58px; }
.web-connect-panel__footer { display: flex; align-items: center; justify-content: space-between; color: #8a96a8; font-size: 12px; }
@media (max-width: 640px) {
  .web-connect-panel__header { display: grid; }
  .web-session-row { grid-template-columns: 1fr; }
  .web-session-row .el-button { width: 100%; }
  .web-connection-stage { min-height: 280px; padding: 18px; }
  .web-qr-frame img { width: min(220px, 68vw); height: auto; }
}
</style>
