<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createSalesUser, deleteSalesUser, getUsers, updateSalesUser } from "@/api/users";
import { getApiErrorMessage } from "@/api/client";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { SalesUserCreate, SalesUser } from "@/types/business";
import { formatDateTime } from "@/utils/format";

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const visible = ref(false);
const editingId = ref("");
const rows = ref<SalesUser[]>([]);
const form = reactive<SalesUserCreate>({
  email: "",
  password: "",
  display_name: "",
  sales_name: "",
  feishu_open_id: "",
});

async function load(): Promise<void> {
  loading.value = true;
  try {
    rows.value = (await getUsers()).data;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

function resetForm(): void {
  Object.assign(form, { email: "", password: "", display_name: "", sales_name: "", feishu_open_id: "" });
}

function openCreate(): void {
  editingId.value = "";
  resetForm();
  visible.value = true;
}

function openEdit(row: SalesUser): void {
  editingId.value = row.id;
  Object.assign(form, {
    email: row.email,
    password: "",
    display_name: row.display_name,
    sales_name: row.sales_name || row.display_name,
    feishu_open_id: row.feishu_open_id || "",
  });
  visible.value = true;
}

async function save(): Promise<void> {
  saving.value = true;
  try {
    if (editingId.value) {
      await updateSalesUser(editingId.value, {
        display_name: form.display_name,
        sales_name: form.sales_name,
        feishu_open_id: form.feishu_open_id,
        password: form.password || undefined,
      });
      ElMessage.success("销售账号已更新");
    } else {
      await createSalesUser(form);
      ElMessage.success("销售账号已创建");
    }
    visible.value = false;
    resetForm();
    await load();
  } catch (requestError) {
    ElMessage.error(getApiErrorMessage(requestError));
  } finally {
    saving.value = false;
  }
}

async function remove(row: SalesUser): Promise<void> {
  await ElMessageBox.confirm(`确认删除销售账号“${row.display_name}”？`, "删除账号", { type: "warning" });
  await deleteSalesUser(row.id);
  ElMessage.success("销售账号已删除");
  await load();
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="用户管理" description="创建销售账号并绑定唯一飞书账号">
      <el-button type="primary" @click="openCreate">创建销售账号</el-button>
    </PageHeader>
    <el-card shadow="never" class="content-card">
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无用户" @retry="load">
        <el-table :data="rows" stripe>
          <el-table-column prop="display_name" label="姓名" />
          <el-table-column prop="email" label="邮箱" min-width="220" />
          <el-table-column prop="role" label="角色" width="100" />
          <el-table-column prop="feishu_open_id" label="飞书 Open ID" min-width="220" />
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }: { row: SalesUser }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }: { row: SalesUser }">
              <template v-if="row.role === 'sales'">
                <el-button text type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button text type="danger" @click="remove(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>
    <el-dialog v-model="visible" :title="editingId ? '编辑销售账号' : '创建销售账号'" width="520px">
      <el-form :model="form" label-position="top">
        <el-form-item label="登录邮箱"><el-input v-model="form.email" :disabled="!!editingId" /></el-form-item>
        <el-form-item :label="editingId ? '新密码（留空不修改）' : '初始密码'">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="后台显示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="销售姓名"><el-input v-model="form.sales_name" /></el-form-item>
        <el-form-item label="飞书 Open ID"><el-input v-model="form.feishu_open_id" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
