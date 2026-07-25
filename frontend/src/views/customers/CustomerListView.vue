<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Plus, Search } from "@element-plus/icons-vue";

import { getApiErrorMessage } from "@/api/client";
import { getCustomers } from "@/api/customers";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import CustomerFormDialog from "@/components/customers/CustomerFormDialog.vue";
import type { Customer } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const error = ref("");
const rows = ref<Customer[]>([]);
const total = ref(0);
const createVisible = ref(false);
const query = reactive({
  page: 1,
  limit: 20,
  search: "",
  lifecycle_stage: "",
});

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const result = await getCustomers({
      limit: query.limit,
      offset: (query.page - 1) * query.limit,
      search: query.search || undefined,
      lifecycle_stage: query.lifecycle_stage || undefined,
    });
    rows.value = result.data;
    total.value = result.total;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

function search(): void {
  query.page = 1;
  void load();
}

function intentTagType(level: string | null): "danger" | "warning" | "success" | "info" {
  if (level === "hot" || level === "high") return "danger";
  if (level === "warm" || level === "medium") return "warning";
  if (level === "low") return "info";
  return "success";
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="客户管理" description="统一管理跨渠道客户资料和销售意向">
      <el-button
        v-permission="'customer.create'"
        type="primary"
        :icon="Plus"
        @click="createVisible = true"
      >
        新建客户
      </el-button>
    </PageHeader>

    <el-card shadow="never" class="content-card">
      <div class="filter-bar">
        <el-input
          v-model="query.search"
          clearable
          placeholder="搜索姓名、公司、邮箱或电话"
          :prefix-icon="Search"
          @keyup.enter="search"
          @clear="search"
        />
        <el-select v-model="query.lifecycle_stage" clearable placeholder="生命周期" @change="search">
          <el-option label="潜在客户" value="lead" />
          <el-option label="已确认商机" value="qualified" />
          <el-option label="客户" value="customer" />
          <el-option label="流失" value="lost" />
        </el-select>
        <el-button @click="search">查询</el-button>
      </div>

      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无客户" @retry="load">
        <el-table :data="rows" stripe>
          <el-table-column label="客户" min-width="220">
            <template #default="{ row }: { row: Customer }">
              <div class="entity-cell">
                <span class="entity-avatar">{{ row.name.slice(0, 1).toUpperCase() }}</span>
                <div><strong>{{ row.name }}</strong><span>{{ row.company_name || "个人客户" }}</span></div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="联系方式" min-width="220">
            <template #default="{ row }: { row: Customer }">
              <div class="stacked-cell"><span>{{ row.email || "—" }}</span><small>{{ row.phone_e164 || "—" }}</small></div>
            </template>
          </el-table-column>
          <el-table-column prop="country_code" label="国家/地区" width="110">
            <template #default="{ row }: { row: Customer }">{{ row.country_code || "—" }}</template>
          </el-table-column>
          <el-table-column label="意向" width="130">
            <template #default="{ row }: { row: Customer }">
              <el-tag :type="intentTagType(row.intent_level)" effect="light">
                {{ row.intent_level || "未评分" }}<template v-if="row.intent_score"> · {{ row.intent_score }}</template>
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="lifecycle_stage" label="阶段" width="130" />
          <el-table-column label="标签" min-width="170">
            <template #default="{ row }: { row: Customer }">
              <el-tag v-for="tag in row.tags.slice(0, 2)" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
              <span v-if="row.tags.length > 2" class="muted-text">+{{ row.tags.length - 2 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }: { row: Customer }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>

      <el-pagination
        v-if="total"
        v-model:current-page="query.page"
        v-model:page-size="query.limit"
        class="table-pagination"
        layout="total, sizes, prev, pager, next"
        :total="total"
        :page-sizes="[20, 50, 100]"
        @change="load"
      />
    </el-card>

    <CustomerFormDialog v-model="createVisible" @created="load" />
  </div>
</template>
