<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { getCustomers } from "@/api/customers";
import { calculateLeadScore, type ScoreSignals } from "@/api/lead-score";
import PageHeader from "@/components/common/PageHeader.vue";
import type { Customer, LeadScoreResult } from "@/types/business";

const customers = ref<Customer[]>([]);
const customerId = ref("");
const calculating = ref(false);
const result = ref<LeadScoreResult | null>(null);
const signals = reactive<ScoreSignals>({
  need_clarity: 50,
  budget_match: 50,
  urgency: 50,
  engagement: 50,
  profile_fit: 50,
});
const signalLabels: Array<{ key: keyof ScoreSignals; label: string; help: string }> = [
  { key: "need_clarity", label: "需求明确度", help: "产品、规格、数量是否清晰" },
  { key: "budget_match", label: "预算匹配度", help: "预算与产品定价的匹配程度" },
  { key: "urgency", label: "采购紧迫度", help: "期望采购和交付时间" },
  { key: "engagement", label: "互动参与度", help: "回复频率与沟通深度" },
  { key: "profile_fit", label: "客户画像匹配", help: "地区、行业与目标客户画像" },
];

async function loadCustomers(): Promise<void> {
  try {
    const page = await getCustomers({ limit: 100, offset: 0 });
    customers.value = page.data;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  }
}

async function calculate(): Promise<void> {
  if (!customerId.value) {
    ElMessage.warning("请先选择客户");
    return;
  }
  calculating.value = true;
  try {
    result.value = await calculateLeadScore(customerId.value, { ...signals });
    ElMessage.success("客户评分已更新");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    calculating.value = false;
  }
}

onMounted(loadCustomers);
</script>

<template>
  <div>
    <PageHeader title="客户评分" description="基于明确业务信号计算客户购买意向" />
    <div class="score-layout">
      <el-card shadow="never" class="content-card">
        <el-form label-position="top">
          <el-form-item label="选择客户">
            <el-select v-model="customerId" filterable placeholder="搜索客户" class="full-width">
              <el-option
                v-for="customer in customers"
                :key="customer.id"
                :label="`${customer.name}${customer.company_name ? ` · ${customer.company_name}` : ''}`"
                :value="customer.id"
              />
            </el-select>
          </el-form-item>
          <div v-for="signal in signalLabels" :key="signal.key" class="score-signal">
            <div><strong>{{ signal.label }}</strong><span>{{ signal.help }}</span></div>
            <el-slider v-model="signals[signal.key]" :step="5" show-input />
          </div>
          <el-button type="primary" :loading="calculating" @click="calculate">计算并保存评分</el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="content-card score-result-card">
        <template v-if="result">
          <div class="score-ring"><strong>{{ result.score }}</strong><span>/ 100</span></div>
          <el-tag size="large" effect="dark">{{ result.level }}</el-tag>
          <p>评分模型：{{ result.scoring_version }}</p>
          <div class="score-breakdown">
            <div v-for="(value, key) in result.components" :key="key">
              <span>{{ key }}</span><strong>{{ value }}</strong>
            </div>
          </div>
        </template>
        <el-empty v-else description="完成左侧信号评估后查看评分结果" />
      </el-card>
    </div>
  </div>
</template>
