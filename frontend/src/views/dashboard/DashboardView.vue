<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ChatDotRound,
  Goods,
  MagicStick,
  Refresh,
  TrendCharts,
  Trophy,
  User,
} from "@element-plus/icons-vue";

import { getApiErrorMessage } from "@/api/client";
import { getDashboardInsights } from "@/api/dashboard";
import ApiState from "@/components/common/ApiState.vue";
import MetricCard from "@/components/common/MetricCard.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { DashboardInsights } from "@/types/business";

const loading = ref(false);
const error = ref("");
const summary = ref<DashboardInsights | null>(null);
const maxRegionValue = computed(() =>
  Math.max(1, ...(summary.value?.region_distribution.map((item) => item.value) ?? [1])),
);
const maxTrendValue = computed(() =>
  Math.max(
    1,
    ...(summary.value?.trend.flatMap((item) => [item.inquiries, item.ai_replies]) ?? [1]),
  ),
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    summary.value = await getDashboardInsights();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="dashboard-page">
    <PageHeader title="销售工作台" description="客户增长、AI 服务与成交机会一览">
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新数据</el-button>
    </PageHeader>

    <ApiState :loading="loading" :error="error" :empty="!summary" empty-text="暂无数据" @retry="load">
      <template v-if="summary">
        <div class="section-title-row">
          <div><span>今日</span><strong>销售概览</strong></div>
          <small>数据根据当前可访问的客户与会话自动汇总</small>
        </div>
        <section class="metric-grid">
          <MetricCard label="今日新增访客" :value="summary.today_visitors" hint="今日新建客户" :icon="User" tone="blue" />
          <MetricCard label="AI 已处理咨询" :value="summary.ai_handled_today" hint="今日 AI 回复" :icon="MagicStick" tone="violet" />
          <MetricCard label="待跟进客户" :value="summary.pending_follow_up" hint="建议优先处理" :icon="ChatDotRound" tone="amber" />
          <MetricCard label="成交机会" :value="summary.won_opportunities" hint="已批准或已成交" :icon="Trophy" tone="green" />
        </section>

        <section class="dashboard-insight-grid">
          <el-card shadow="never" class="content-card region-card">
            <template #header>
              <div class="card-heading">
                <div><strong>客户地区分布</strong><span>按客户国家信息自动归类</span></div>
                <el-icon><TrendCharts /></el-icon>
              </div>
            </template>
            <div v-if="summary.region_distribution.length" class="region-list">
              <div v-for="region in summary.region_distribution" :key="region.name" class="region-row">
                <div><strong>{{ region.name }}</strong><span>{{ region.value }} 位客户</span></div>
                <div class="region-progress"><i :style="{ width: `${(region.value / maxRegionValue) * 100}%` }" /></div>
              </div>
            </div>
            <el-empty v-else description="暂无数据" />
          </el-card>

          <el-card shadow="never" class="content-card product-rank-card">
            <template #header>
              <div class="card-heading">
                <div><strong>热门产品排行</strong><span>根据客户咨询内容统计</span></div>
                <el-icon><Goods /></el-icon>
              </div>
            </template>
            <div v-if="summary.popular_products.length" class="product-rank-list">
              <div v-for="(product, index) in summary.popular_products" :key="product.name" class="product-rank-item">
                <span class="rank-number">{{ index + 1 }}</span>
                <div><strong>{{ product.name }}</strong><small>单位 {{ product.unit }}</small></div>
                <b>{{ product.inquiries }} 次</b>
              </div>
            </div>
            <el-empty v-else description="暂无数据" />
          </el-card>

          <el-card shadow="never" class="content-card assistant-status-card">
            <template #header>
              <div class="card-heading">
                <div><strong>AI 销售助手状态</strong><span>今日智能服务表现</span></div>
                <span class="live-status"><i />运行中</span>
              </div>
            </template>
            <div class="assistant-metric">
              <span>今日 AI 回复数量</span><strong>{{ summary.ai_handled_today }}</strong>
            </div>
            <div class="assistant-metric">
              <span>成功识别客户数量</span><strong>{{ summary.identified_customers_today }}</strong>
            </div>
            <div class="assistant-metric assistant-metric--accent">
              <span>高意向客户数量</span><strong>{{ summary.high_intent_customers }}</strong>
            </div>
          </el-card>
        </section>

        <el-card shadow="never" class="content-card trend-card dashboard-trend-card">
          <template #header>
            <div class="card-heading">
              <div><strong>近 7 日咨询趋势</strong><span>客户咨询与 AI 回复对比</span></div>
              <div class="chart-legend">
                <span><i class="legend-dot legend-dot--inquiry" />客户咨询</span>
                <span><i class="legend-dot legend-dot--ai" />AI 回复</span>
              </div>
            </div>
          </template>
          <div v-if="summary.trend.some((item) => item.inquiries || item.ai_replies)" class="trend-chart">
            <div v-for="point in summary.trend" :key="point.date" class="trend-column">
              <div class="trend-values"><span>{{ point.inquiries }}</span><span>{{ point.ai_replies }}</span></div>
              <div class="trend-bars">
                <i class="trend-bar trend-bar--inquiry" :style="{ height: `${Math.max(4, (point.inquiries / maxTrendValue) * 100)}%` }" />
                <i class="trend-bar trend-bar--ai" :style="{ height: `${Math.max(4, (point.ai_replies / maxTrendValue) * 100)}%` }" />
              </div>
              <small>{{ point.date.slice(5) }}</small>
            </div>
          </div>
          <el-empty v-else description="暂无数据" />
        </el-card>
      </template>
    </ApiState>
  </div>
</template>
