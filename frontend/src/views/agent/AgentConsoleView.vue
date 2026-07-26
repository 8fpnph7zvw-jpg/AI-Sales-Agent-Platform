<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { MagicStick, Promotion } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import { chatWithAgent } from "@/api/agent";
import { getApiErrorMessage } from "@/api/client";
import { createConversation } from "@/api/conversations";
import { getCustomers } from "@/api/customers";
import PageHeader from "@/components/common/PageHeader.vue";
import type { AgentChatResult, Customer } from "@/types/business";
import { createUuid } from "@/utils/uuid";

const formRef = ref<FormInstance>();
const customerLoading = ref(false);
const submitting = ref(false);
const customers = ref<Customer[]>([]);
const result = ref<AgentChatResult | null>(null);
const conversationId = ref("");
const conversationCustomerId = ref("");
const form = reactive({
  customer_id: "",
  query: "",
});
const rules: FormRules = {
  customer_id: [{ required: true, message: "请选择客户", trigger: "change" }],
  query: [{ required: true, message: "请输入客户问题", trigger: "blur" }],
};

async function loadCustomers(): Promise<void> {
  customerLoading.value = true;
  try {
    customers.value = (await getCustomers({ limit: 100, offset: 0 })).data;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    customerLoading.value = false;
  }
}

function customerChanged(): void {
  conversationId.value = "";
  conversationCustomerId.value = "";
  result.value = null;
}

async function ensureConversation(): Promise<string> {
  if (
    conversationId.value &&
    conversationCustomerId.value === form.customer_id
  ) {
    return conversationId.value;
  }
  const customer = customers.value.find((item) => item.id === form.customer_id);
  const conversation = await createConversation({
    customer_id: form.customer_id,
    subject: `AI Agent Demo - ${customer?.name || "Customer"}`,
  });
  conversationId.value = conversation.id;
  conversationCustomerId.value = form.customer_id;
  return conversation.id;
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return;
  submitting.value = true;
  result.value = null;
  try {
    const activeConversationId = await ensureConversation();
    result.value = await chatWithAgent({
      conversation_id: activeConversationId,
      query: form.query,
      idempotency_key: createUuid(),
      inputs: {},
    });
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    submitting.value = false;
  }
}

onMounted(loadCustomers);
</script>

<template>
  <div>
    <PageHeader
      title="AI 客服"
      description="选择客户并输入问题，系统会自动创建会话并调用销售 Agent"
    />
    <div class="agent-workspace">
      <el-card shadow="never" class="content-card agent-compose">
        <div class="agent-badge">
          <el-icon><MagicStick /></el-icon>
          Agent Console
        </div>
        <h2>向销售 Agent 发起请求</h2>
        <p>无需查找或填写 conversation ID，首次提问时会自动创建客户会话。</p>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="客户" prop="customer_id">
            <el-select
              v-model="form.customer_id"
              class="full-width"
              filterable
              :loading="customerLoading"
              placeholder="请选择测试客户"
              @change="customerChanged"
            >
              <el-option
                v-for="customer in customers"
                :key="customer.id"
                :label="customer.company_name || customer.name"
                :value="customer.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="客户问题" prop="query">
            <el-input
              v-model="form.query"
              type="textarea"
              :rows="8"
              maxlength="20000"
              show-word-limit
              placeholder="例如：Wireless Earphone 订购 500 件的价格、交期和运输方式是什么？"
            />
          </el-form-item>
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="submitting"
            @click="submit"
          >
            运行 Agent
          </el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="content-card agent-result">
        <template #header>
          <div class="card-heading">
            <div>
              <strong>AI 回复</strong>
              <span>模型输出与知识引用</span>
            </div>
          </div>
        </template>
        <div v-if="submitting" class="agent-thinking">
          <span /><span /><span />
          <p>Agent 正在分析客户需求…</p>
        </div>
        <div v-else-if="result" class="agent-answer">
          <div class="agent-answer__content">{{ result.answer }}</div>
          <div class="agent-answer__meta">
            <span>会话 {{ result.conversation_id }}</span>
            <span>耗时 {{ result.usage.latency_ms ?? "—" }} ms</span>
            <span>
              Token
              {{ (result.usage.prompt_tokens ?? 0) + (result.usage.completion_tokens ?? 0) }}
            </span>
            <span>引用 {{ result.citations.length }}</span>
          </div>
          <el-collapse v-if="result.citations.length">
            <el-collapse-item title="查看知识引用">
              <pre>{{ JSON.stringify(result.citations, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-empty v-else description="选择客户并提交问题后，AI 回复将显示在这里" />
      </el-card>
    </div>
  </div>
</template>
