<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ChatLineRound, Delete, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type TableInstance } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import {
  deleteConversation,
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
const deleting = ref(false);
const error = ref("");
const rows = ref<Conversation[]>([]);
const total = ref(0);
const selected = ref<Conversation | null>(null);
const messages = ref<Message[]>([]);
const messageText = ref("");
const tableRef = ref<TableInstance>();
const selectedRows = ref<Conversation[]>([]);
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

function selectCurrentPage(): void {
  tableRef.value?.toggleAllSelection();
}

async function removeConversations(targets: Conversation[]): Promise<void> {
  if (!targets.length || deleting.value) return;
  const label = targets.length === 1
    ? `“${targets[0].customer_name || targets[0].customer_id}”的聊天记录`
    : `选中的 ${targets.length} 条聊天记录`;
  try {
    await ElMessageBox.confirm(
      `确定删除${label}吗？删除后将无法从列表中恢复。`,
      "确认删除",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }

  deleting.value = true;
  const results = await Promise.allSettled(targets.map((item) => deleteConversation(item.id)));
  const failed = results.filter((result) => result.status === "rejected");
  if (failed.length) {
    const first = failed[0] as PromiseRejectedResult;
    ElMessage.error(
      failed.length === targets.length
        ? getApiErrorMessage(first.reason)
        : `${targets.length - failed.length} 条已删除，${failed.length} 条删除失败`,
    );
  } else {
    ElMessage.success(targets.length === 1 ? "聊天记录已删除" : `已删除 ${targets.length} 条聊天记录`);
  }
  if (selected.value && targets.some((item) => item.id === selected.value?.id)) selected.value = null;
  selectedRows.value = [];
  deleting.value = false;
  await load();
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="聊天记录" description="查看跨渠道客户会话及消息历史" />
    <el-card shadow="never" class="content-card">
      <div class="filter-bar filter-bar--with-actions">
        <el-input v-model="query.search" clearable placeholder="搜索客户或会话" :prefix-icon="Search" @keyup.enter="load" />
        <el-select v-model="query.status" clearable placeholder="会话状态" @change="load">
          <el-option label="进行中" value="open" />
          <el-option label="待处理" value="pending" />
          <el-option label="已关闭" value="closed" />
        </el-select>
        <el-button @click="load">查询</el-button>
        <span class="filter-bar__spacer" />
        <el-button @click="selectCurrentPage">全选本页</el-button>
        <el-button
          type="danger"
          plain
          :icon="Delete"
          :loading="deleting"
          :disabled="!selectedRows.length"
          @click="removeConversations(selectedRows)"
        >
          批量删除<span v-if="selectedRows.length">（{{ selectedRows.length }}）</span>
        </el-button>
      </div>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无会话记录" @retry="load">
        <el-table
          ref="tableRef"
          :data="rows"
          row-key="id"
          @row-click="openConversation"
          @selection-change="selectedRows = $event"
        >
          <el-table-column type="selection" width="48" reserve-selection />
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
          <el-table-column label="操作" width="92" fixed="right">
            <template #default="{ row }: { row: Conversation }">
              <el-button
                text
                type="danger"
                :icon="Delete"
                :loading="deleting"
                @click.stop="removeConversations([row])"
              >删除</el-button>
            </template>
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
