<script setup lang="ts">
import { reactive, ref } from "vue";
import { MagicStick, Promotion } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import { chatWithAgent } from "@/api/agent";
import { getApiErrorMessage } from "@/api/client";
import PageHeader from "@/components/common/PageHeader.vue";
import type { AgentChatResult } from "@/types/business";

const formRef = ref<FormInstance>();
const submitting = ref(false);
const result = ref<AgentChatResult | null>(null);
const form = reactive({
  conversation_id: "",
  query: "",
});
const rules: FormRules = {
  conversation_id: [
    { required: true, message: "请输入会话 ID", trigger: "blur" },
    { len: 26, message: "会话 ID 应为 26 位", trigger: "blur" },
  ],
  query: [{ required: true, message: "请输入客户问题", trigger: "blur" }],
};

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return;
  submitting.value = true;
  result.value = null;
  try {
    result.value = await chatWithAgent({
      conversation_id: form.conversation_id,
      query: form.query,
      idempotency_key: crypto.randomUUID(),
      inputs: {},
    });
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div>
    <PageHeader title="AI客服" description="通过 Dify Agent 测试并处理指定客户会话" />
    <div class="agent-workspace">
      <el-card shadow="never" class="content-card agent-compose">
        <div class="agent-badge"><el-icon><MagicStick /></el-icon> Agent Console</div>
        <h2>向销售 Agent 发起请求</h2>
        <p>请求将发送至后端，由服务端安全调用 Dify Agent API。</p>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="会话 ID" prop="conversation_id">
            <el-input v-model="form.conversation_id" maxlength="26" placeholder="客户会话 public_id" />
          </el-form-item>
          <el-form-item label="客户问题" prop="query">
            <el-input
              v-model="form.query"
              type="textarea"
              :rows="8"
              maxlength="20000"
              show-word-limit
              placeholder="输入客户的产品需求、预算或交付问题"
            />
          </el-form-item>
          <el-button type="primary" :icon="Promotion" :loading="submitting" @click="submit">
            运行 Agent
          </el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="content-card agent-result">
        <template #header>
          <div class="card-heading"><div><strong>AI 回复</strong><span>模型输出与调用信息</span></div></div>
        </template>
        <div v-if="submitting" class="agent-thinking">
          <span /><span /><span />
          <p>Agent 正在分析客户需求…</p>
        </div>
        <div v-else-if="result" class="agent-answer">
          <div class="agent-answer__content">{{ result.answer }}</div>
          <div class="agent-answer__meta">
            <span>耗时 {{ result.usage.latency_ms ?? "—" }} ms</span>
            <span>Token {{ (result.usage.prompt_tokens ?? 0) + (result.usage.completion_tokens ?? 0) }}</span>
            <span>引用 {{ result.citations.length }}</span>
          </div>
          <el-collapse v-if="result.citations.length">
            <el-collapse-item title="查看知识引用">
              <pre>{{ JSON.stringify(result.citations, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-empty v-else description="提交客户问题后，AI 回复将显示在这里" />
      </el-card>
    </div>
  </div>
</template>
