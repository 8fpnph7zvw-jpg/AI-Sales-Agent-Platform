<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Delete } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { getCustomers } from "@/api/customers";
import {
  deleteLeadScoreHistory,
  getLeadScoreHistory,
  getLeadScores,
  runLeadScoringWorkflow,
} from "@/api/lead-score";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";
import type { Customer, CustomerCurrentScore, CustomerScore } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const auth = useAuthStore();
const loading = ref(false);
const running = ref(false);
const error = ref("");
const rows = ref<CustomerCurrentScore[]>([]);
const customers = ref<Customer[]>([]);
const total = ref(0);
const histories = reactive<Record<string, CustomerScore[]>>({});
const historyLoading = reactive<Record<string, boolean>>({});
const deletingScoreId = ref<number | null>(null);
const form = reactive({ customer_id: "", product_requirement: "", quantity: "" });

const categoryLabels: Record<CustomerCurrentScore["category"], string> = {
  potential: "潜在客户",
  follow_up: "待跟进客户",
  quoted: "已报价客户",
  customer: "已成交客户",
  vip: "VIP客户",
};

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [scores, customerPage] = await Promise.all([
      getLeadScores({ limit: 100, offset: 0 }),
      getCustomers({ limit: 100, offset: 0 }),
    ]);
    rows.value = scores.data;
    total.value = scores.total;
    customers.value = customerPage.data;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

async function loadHistory(customerId: string): Promise<void> {
  historyLoading[customerId] = true;
  try {
    histories[customerId] = (
      await getLeadScoreHistory(customerId, { limit: 100, offset: 0 })
    ).data;
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    historyLoading[customerId] = false;
  }
}

function handleExpand(row: CustomerCurrentScore, expandedRows: CustomerCurrentScore[]): void {
  if (expandedRows.some((item) => item.customer_id === row.customer_id)) {
    void loadHistory(row.customer_id);
  }
}

async function removeHistory(row: CustomerCurrentScore, score: CustomerScore): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.customer_name} 的这条历史评分吗？客户资料不会被删除。`,
      "删除历史评分",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  deletingScoreId.value = score.id;
  try {
    await deleteLeadScoreHistory(row.customer_id, score.id);
    ElMessage.success("历史评分已删除");
    await Promise.all([load(), loadHistory(row.customer_id)]);
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    deletingScoreId.value = null;
  }
}

async function runWorkflow(): Promise<void> {
  if (!form.customer_id) {
    ElMessage.warning("请选择客户");
    return;
  }
  running.value = true;
  try {
    await runLeadScoringWorkflow({ ...form });
    ElMessage.success("Dify 评分 Workflow 已完成");
    await load();
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    running.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="客户评分结果" description="展示客户当前评分，展开可查看历史评分记录" />
    <el-card v-if="auth.canAny(['customer.score'])" shadow="never" class="content-card">
      <template #header><strong>手动触发评分（管理员）</strong></template>
      <el-form :model="form" label-position="top" class="filter-bar">
        <el-form-item label="客户">
          <el-select v-model="form.customer_id" filterable placeholder="选择客户">
            <el-option
              v-for="customer in customers"
              :key="customer.id"
              :label="customer.name"
              :value="customer.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="产品需求"><el-input v-model="form.product_requirement" /></el-form-item>
        <el-form-item label="数量"><el-input v-model="form.quantity" /></el-form-item>
        <el-button type="primary" :loading="running" @click="runWorkflow">
          运行评分 Workflow
        </el-button>
      </el-form>
    </el-card>
    <el-card shadow="never" class="content-card">
      <template #header><strong>客户当前评分（{{ total }}）</strong></template>
      <ApiState
        :loading="loading"
        :error="error"
        :empty="!rows.length"
        empty-text="暂无评分记录"
        @retry="load"
      >
        <el-table :data="rows" stripe row-key="customer_id" @expand-change="handleExpand">
          <el-table-column type="expand">
            <template #default="{ row }: { row: CustomerCurrentScore }">
              <div v-loading="historyLoading[row.customer_id]" class="history-panel">
                <el-table :data="histories[row.customer_id] || []" size="small">
                  <el-table-column prop="score" label="评分" width="90" />
                  <el-table-column prop="level" label="等级" width="90" />
                  <el-table-column prop="reason" label="原因" min-width="300" />
                  <el-table-column label="评分时间" width="180">
                    <template #default="{ row: score }: { row: CustomerScore }">
                      {{ formatDateTime(score.created_time) }}
                    </template>
                  </el-table-column>
                  <el-table-column v-if="auth.canAny(['customer.score'])" label="操作" width="100">
                    <template #default="{ row: score }: { row: CustomerScore }">
                      <el-button
                        text
                        type="danger"
                        :icon="Delete"
                        :loading="deletingScoreId === score.id"
                        @click="removeHistory(row, score)"
                      >删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="customer_name" label="客户" min-width="200" />
          <el-table-column prop="intent_score" label="当前评分" width="110" />
          <el-table-column prop="intent_level" label="等级" width="100" />
          <el-table-column label="客户分类" width="140">
            <template #default="{ row }: { row: CustomerCurrentScore }">
              <el-tag>{{ categoryLabels[row.category] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最后评分时间" width="180">
            <template #default="{ row }: { row: CustomerCurrentScore }">
              {{ row.last_scored_at ? formatDateTime(row.last_scored_at) : "—" }}
            </template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>
  </div>
</template>

<style scoped>
.history-panel {
  padding: 12px 48px;
  min-height: 80px;
}
</style>
