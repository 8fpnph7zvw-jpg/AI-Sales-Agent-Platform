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
        sub-title="请在 Connector 管理中选择 WhatsApp Cloud API，或使用 WhatsApp Web 扫码登录。"
      >
        <template #extra>
          <el-button type="primary" :icon="Link" @click="router.push('/connectors')">
            前往 Connector 管理
          </el-button>
        </template>
      </el-result>
      <el-alert
        title="Cloud API 凭据加密保存；WhatsApp Web 会话通过 FastAPI 安全代理并使用 LocalAuth 持久化。"
        type="success"
        show-icon
        :closable="false"
      />
    </el-card>
  </div>
</template>
