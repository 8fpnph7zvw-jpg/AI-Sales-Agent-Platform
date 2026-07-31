<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Delete, Edit, Plus, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { deleteCustomer, getCustomers, updateCustomer } from "@/api/customers";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import CustomerFormDialog from "@/components/customers/CustomerFormDialog.vue";
import {
  CUSTOMER_CATEGORY_PREFIX,
  customerCategoryOptions,
  getCustomerCategory,
  getCustomerCategoryOption,
  withCustomerCategory,
  type CustomerCategory,
} from "@/constants/customers";
import type { Customer } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const error = ref("");
const rows = ref<Customer[]>([]);
const total = ref(0);
const createVisible = ref(false);
const editVisible = ref(false);
const editing = ref<Customer | null>(null);
const savingCategory = ref(false);
const deletingId = ref("");
const editForm = reactive<{ lifecycle_stage: CustomerCategory }>({ lifecycle_stage: "lead" });
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

function openCategoryEditor(row: Customer): void {
  editing.value = row;
  editForm.lifecycle_stage = getCustomerCategory(row);
  editVisible.value = true;
}

async function saveCategory(): Promise<void> {
  if (!editing.value || savingCategory.value) return;
  savingCategory.value = true;
  try {
    const updated = await updateCustomer(editing.value.id, {
      lifecycle_stage: editForm.lifecycle_stage,
      tags: withCustomerCategory(editing.value.tags, editForm.lifecycle_stage),
    });
    const index = rows.value.findIndex((item) => item.id === updated.id);
    if (index >= 0) rows.value[index] = updated;
    ElMessage.success("客户分类已更新");
    editVisible.value = false;
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    savingCategory.value = false;
  }
}

async function removeCustomer(row: Customer): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除客户“${row.name}”吗？此操作需要二次确认。`,
      "删除客户",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  deletingId.value = row.id;
  try {
    await deleteCustomer(row.id);
    ElMessage.success("客户已删除");
    if (rows.value.length === 1 && query.page > 1) query.page -= 1;
    await load();
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    deletingId.value = "";
  }
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
        <el-select v-model="query.lifecycle_stage" clearable placeholder="客户分类" @change="search">
          <el-option
            v-for="option in customerCategoryOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
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
          <el-table-column label="客户分类" width="140">
            <template #default="{ row }: { row: Customer }">
              <el-tag :type="getCustomerCategoryOption(row).type" effect="light" round>
                {{ getCustomerCategoryOption(row).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="标签" min-width="170">
            <template #default="{ row }: { row: Customer }">
              <el-tag
                v-for="tag in row.tags.filter((item) => !item.startsWith(CUSTOMER_CATEGORY_PREFIX)).slice(0, 2)"
                :key="tag"
                size="small"
                effect="plain"
              >{{ tag }}</el-tag>
              <span v-if="!row.tags.filter((item) => !item.startsWith(CUSTOMER_CATEGORY_PREFIX)).length" class="muted-text">—</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }: { row: Customer }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }: { row: Customer }">
              <el-button
                v-permission="['customer.update_own', 'customer.update_all']"
                text
                type="primary"
                :icon="Edit"
                @click="openCategoryEditor(row)"
              >分类</el-button>
              <el-button
                v-permission="'customer.delete'"
                text
                type="danger"
                :icon="Delete"
                :loading="deletingId === row.id"
                @click="removeCustomer(row)"
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
        layout="total, sizes, prev, pager, next"
        :total="total"
        :page-sizes="[20, 50, 100]"
        @change="load"
      />
    </el-card>

    <CustomerFormDialog v-model="createVisible" @created="load" />

    <el-dialog v-model="editVisible" title="编辑客户分类" width="460px" destroy-on-close>
      <el-form :model="editForm" label-position="top">
        <el-form-item label="客户">
          <div class="readonly-field"><strong>{{ editing?.name }}</strong><small>{{ editing?.company_name || "个人客户" }}</small></div>
        </el-form-item>
        <el-form-item label="客户分类" required>
          <el-select v-model="editForm.lifecycle_stage" class="full-width">
            <el-option
              v-for="option in customerCategoryOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingCategory" @click="saveCategory">保存分类</el-button>
      </template>
    </el-dialog>
  </div>
</template>
