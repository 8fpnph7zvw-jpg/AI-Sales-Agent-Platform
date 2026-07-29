<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ChatLineRound, Search } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import {
  getConversationMessages,
  getConversations,
  sendConversationMessage,
} from "@/api/conversations";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { Conversation, Message } from "@/types/business";
import { formatDateTime } from "@/utils/format";
import { createUuid } from "@/utils/uuid";

const loading = ref(false);
const messageLoading = ref(false);
const sending = ref(false);
const error = ref("");
const rows = ref<Conversation[]>([]);
const total = ref(0);
const selected = ref<Conversation | null>(null);
const messages = ref<Message[]>([]);
const messageText = ref("");
const query = reactive({ page: 1, limit: 20, search: "", status: "" });
const sourceLabels = {
  whatsapp: "WhatsApp",
  admin_test: "后台测试",
  web: "Web",
} as const;

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const result = await getConversations({
      limit: query.limit,
      offset: (query.page - 1) * query.limit,
      search: query.search || undefined,
      status: query.status || undefined,
    });
    rows.value = result.data;
    total.value = result.total;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

async function openConversation(row: Conversation): Promise<void> {
  selected.value = row;
  messageLoading.value = true;
  try {
    const result = await getConversationMessages(row.id, { limit: 100 });
    messages.value = result.data;
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    messageLoading.value = false;
  }
}

async function send(): Promise<void> {
  if (!selected.value || !messageText.value.trim()) return;
  sending.value = true;
  try {
    const message = await sendConversationMessage({
      conversation_id: selected.value.id,
      content: messageText.value.trim(),
      message_type: "text",
      idempotency_key: createUuid(),
    });
    messages.value.push(message);
    messageText.value = "";
    ElMessage.success(message.status === "sent" ? "消息已发送到 WhatsApp" : "消息已进入发送队列");
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    sending.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="聊天记录" description="查看跨渠道客户会话及消息历史" />
    <el-card shadow="never" class="content-card">
      <div class="filter-bar">
        <el-input v-model="query.search" clearable placeholder="搜索客户或会话" :prefix-icon="Search" @keyup.enter="load" />
        <el-select v-model="query.status" clearable placeholder="会话状态" @change="load">
          <el-option label="进行中" value="open" />
          <el-option label="待处理" value="pending" />
          <el-option label="已关闭" value="closed" />
        </el-select>
        <el-button @click="load">查询</el-button>
      </div>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无会话记录" @retry="load">
        <el-table :data="rows" @row-click="openConversation">
          <el-table-column label="客户" min-width="180">
            <template #default="{ row }: { row: Conversation }"><strong>{{ row.customer_name || row.customer_id }}</strong></template>
          </el-table-column>
          <el-table-column prop="channel" label="渠道" width="120" />
          <el-table-column label="最后消息" min-width="280">
            <template #default="{ row }: { row: Conversation }"><span class="ellipsis">{{ row.last_message_preview || "—" }}</span></template>
          </el-table-column>
          <el-table-column label="AI状态" width="110">
            <template #default="{ row }: { row: Conversation }"><el-tag effect="plain">{{ row.ai_status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }: { row: Conversation }"><el-tag :type="row.status === 'open' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }: { row: Conversation }">{{ formatDateTime(row.last_message_at) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>
      <el-pagination
        v-if="total"
        v-model:current-page="query.page"
        v-model:page-size="query.limit"
        class="table-pagination"
        layout="total, prev, pager, next"
        :total="total"
        @change="load"
      />
    </el-card>

    <el-drawer v-model="selected" :title="selected?.customer_name || '会话详情'" size="520px">
      <div v-loading="messageLoading" class="message-thread">
        <div
          v-for="message in messages"
          :key="message.id"
          class="message-bubble"
          :class="{ 'message-bubble--outbound': message.direction === 'outbound' }"
        >
          <small>
            {{ message.sender_type }} ·
            {{ sourceLabels[message.source] || message.source }} ·
            {{ formatDateTime(message.created_at) }}
          </small>
          <p>{{ message.content }}</p>
          <span>{{ message.status }}</span>
        </div>
        <el-empty v-if="!messageLoading && !messages.length" description="暂无消息" />
      </div>
      <template #footer>
        <div v-permission="'message.send'" class="message-composer">
          <el-input v-model="messageText" type="textarea" :rows="2" placeholder="输入回复内容" @keyup.ctrl.enter="send" />
          <el-button type="primary" :icon="ChatLineRound" :loading="sending" @click="send">发送</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>
