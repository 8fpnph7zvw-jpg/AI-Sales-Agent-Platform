<script setup lang="ts">
import { Connection, Link } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <div class="whatsapp-page">
    <div class="enterprise-page-header">
      <div>
        <span class="eyebrow">CHANNEL OPERATIONS</span>
        <h1>WhatsApp Connector</h1>
        <p>通过统一 Connector 接口管理 WhatsApp Business 渠道和 provider adapter。</p>
      </div>
      <el-button type="primary" :icon="Connection" @click="router.push('/connectors')">
        管理 Connector
      </el-button>
    </div>

    <el-card shadow="never">
      <el-result
        icon="info"
        title="使用 Provider Adapter 配置连接"
        sub-title="二维码会话流程已停用。请在 Connector 管理中配置 WhatsApp Cloud API 凭据并测试连接。"
      >
        <template #extra>
          <el-button type="primary" :icon="Link" @click="router.push('/connectors')">
            前往 Connector 管理
          </el-button>
        </template>
      </el-result>
      <el-alert
        title="Webhook URL 按 Connector 独立生成；Access Token、Verify Token 和 App Secret 均加密保存。"
        type="success"
        show-icon
        :closable="false"
      />
    </el-card>
  </div>
</template>
