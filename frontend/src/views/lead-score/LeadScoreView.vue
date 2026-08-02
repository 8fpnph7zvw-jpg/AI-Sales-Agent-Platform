<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getApiErrorMessage } from "@/api/client";
import { getCustomers } from "@/api/customers";
import { getLeadScores, runLeadScoringWorkflow } from "@/api/lead-score";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";
import type { Customer, CustomerScore } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const auth = useAuthStore();
const loading = ref(false);
const running = ref(false);
const error = ref("");
const rows = ref<CustomerScore[]>([]);
const customers = ref<Customer[]>([]);
const total = ref(0);
const form = reactive({ customer_id: "", product_requirement: "", quantity: "" });

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
    <PageHeader title="客户评分结果" description="Dify Lead Scoring Workflow 的历史评分记录" />
    <el-card v-if="auth.canAny(['customer.score'])" shadow="never" class="content-card">
      <template #header><strong>手动触发评分（管理员）</strong></template>
      <el-form :model="form" label-position="top" class="filter-bar">
        <el-form-item label="客户">
          <el-select v-model="form.customer_id" filterable placeholder="选择客户">
            <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品需求"><el-input v-model="form.product_requirement" /></el-form-item>
        <el-form-item label="数量"><el-input v-model="form.quantity" /></el-form-item>
        <el-button type="primary" :loading="running" @click="runWorkflow">运行评分 Workflow</el-button>
      </el-form>
    </el-card>
    <el-card shadow="never" class="content-card">
      <template #header><strong>评分记录（{{ total }}）</strong></template>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无评分记录" @retry="load">
        <el-table :data="rows" stripe>
          <el-table-column prop="customer_name" label="客户" min-width="180" />
          <el-table-column prop="score" label="评分" width="90" />
          <el-table-column prop="level" label="等级" width="90" />
          <el-table-column label="需要跟进" width="110">
            <template #default="{ row }: { row: CustomerScore }">
              <el-tag :type="row.need_follow ? 'danger' : 'info'">{{ row.need_follow ? "是" : "否" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="300" show-overflow-tooltip />
          <el-table-column label="评分时间" width="180">
            <template #default="{ row }: { row: CustomerScore }">{{ formatDateTime(row.created_time) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>
  </div>
</template>
