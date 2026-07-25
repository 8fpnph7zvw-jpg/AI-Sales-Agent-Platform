<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Plus, Refresh } from "@element-plus/icons-vue";

import { getApiErrorMessage } from "@/api/client";
import { getWorkflows } from "@/api/workflows";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { Workflow } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const error = ref("");
const rows = ref<Workflow[]>([]);
const total = ref(0);
const query = reactive({ page: 1, limit: 20, status: "" });

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const result = await getWorkflows({
      limit: query.limit,
      offset: (query.page - 1) * query.limit,
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

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="Workflow管理" description="管理询盘分配、通知和跟进自动化流程">
      <el-button v-permission="'workflow.manage'" type="primary" :icon="Plus" disabled>新建工作流</el-button>
    </PageHeader>
    <el-card shadow="never" class="content-card">
      <div class="filter-bar">
        <el-select v-model="query.status" clearable placeholder="工作流状态" @change="load">
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
          <el-option label="已停用" value="disabled" />
        </el-select>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无工作流" @retry="load">
        <el-table :data="rows">
          <el-table-column label="工作流" min-width="240">
            <template #default="{ row }: { row: Workflow }">
              <div class="stacked-cell"><strong>{{ row.name }}</strong><small>{{ row.description || "无描述" }}</small></div>
            </template>
          </el-table-column>
          <el-table-column prop="trigger_type" label="触发方式" width="150" />
          <el-table-column prop="version" label="版本" width="90" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }: { row: Workflow }"><el-tag :type="row.status === 'published' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }: { row: Workflow }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>
  </div>
</template>
