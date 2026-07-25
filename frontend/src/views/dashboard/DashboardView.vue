<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ChatDotRound,
  Clock,
  DocumentChecked,
  TrendCharts,
  User,
} from "@element-plus/icons-vue";

import { getDashboardSummary } from "@/api/dashboard";
import { getApiErrorMessage } from "@/api/client";
import ApiState from "@/components/common/ApiState.vue";
import MetricCard from "@/components/common/MetricCard.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { DashboardSummary } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const error = ref("");
const summary = ref<DashboardSummary | null>(null);
const maxTrendValue = computed(() =>
  Math.max(1, ...(summary.value?.trend.map((item) => item.inquiries) ?? [1])),
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    summary.value = await getDashboardSummary();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="Dashboard" description="销售询盘与 AI 服务运行概览">
      <el-button :loading="loading" @click="load">刷新数据</el-button>
    </PageHeader>

    <ApiState :loading="loading" :error="error" :empty="!summary" @retry="load">
      <template v-if="summary">
        <section class="metric-grid">
          <MetricCard label="客户总数" :value="summary.customer_total" :icon="User" tone="blue" />
          <MetricCard
            label="活跃会话"
            :value="summary.active_conversations"
            :icon="ChatDotRound"
            tone="violet"
          />
          <MetricCard
            label="高意向客户"
            :value="summary.high_intent_customers"
            :icon="TrendCharts"
            tone="green"
          />
          <MetricCard
            label="待处理报价"
            :value="summary.pending_quotations"
            :icon="DocumentChecked"
            tone="amber"
          />
        </section>

        <section class="dashboard-grid">
          <el-card shadow="never" class="content-card trend-card">
            <template #header>
              <div class="card-heading">
                <div><strong>询盘趋势</strong><span>AI 回复与客户询盘</span></div>
                <el-tag effect="plain">{{ summary.ai_resolution_rate }}% AI解决率</el-tag>
              </div>
            </template>
            <div v-if="summary.trend.length" class="trend-chart">
              <div v-for="point in summary.trend" :key="point.date" class="trend-column">
                <div class="trend-bars">
                  <span
                    class="trend-bar trend-bar--inquiry"
                    :style="{ height: `${Math.max(8, (point.inquiries / maxTrendValue) * 100)}%` }"
                  />
                  <span
                    class="trend-bar trend-bar--ai"
                    :style="{ height: `${Math.max(8, (point.ai_replies / maxTrendValue) * 100)}%` }"
                  />
                </div>
                <small>{{ point.date.slice(5) }}</small>
              </div>
            </div>
            <el-empty v-else description="暂无趋势数据" />
            <div class="chart-legend">
              <span><i class="legend-dot legend-dot--inquiry" />客户询盘</span>
              <span><i class="legend-dot legend-dot--ai" />AI 回复</span>
            </div>
          </el-card>

          <el-card shadow="never" class="content-card activity-card">
            <template #header>
              <div class="card-heading">
                <div><strong>最近动态</strong><span>关键业务事件</span></div>
                <el-icon><Clock /></el-icon>
              </div>
            </template>
            <div v-if="summary.recent_activities.length" class="activity-list">
              <div v-for="activity in summary.recent_activities" :key="activity.id" class="activity-item">
                <span class="activity-item__dot" />
                <div>
                  <strong>{{ activity.title }}</strong>
                  <p>{{ activity.type }} · {{ formatDateTime(activity.occurred_at) }}</p>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无业务动态" />
          </el-card>
        </section>
      </template>
    </ApiState>
  </div>
</template>
