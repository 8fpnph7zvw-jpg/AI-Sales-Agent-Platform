<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { createCustomer } from "@/api/customers";
import type { CustomerCreate } from "@/types/business";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  created: [];
}>();

const formRef = ref<FormInstance>();
const saving = ref(false);
const form = reactive<CustomerCreate>({
  name: "",
  company_name: "",
  email: "",
  phone_e164: "",
  country_code: "",
  language: "",
  source_type: "",
  tags: [],
  notes: "",
});
const rules: FormRules = {
  name: [{ required: true, message: "请输入客户姓名", trigger: "blur" }],
  email: [{ type: "email", message: "邮箱格式不正确", trigger: "blur" }],
  country_code: [{ len: 2, message: "请输入两位国家代码", trigger: "blur" }],
};

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    formRef.value?.resetFields();
    Object.assign(form, {
      name: "",
      company_name: "",
      email: "",
      phone_e164: "",
      country_code: "",
      language: "",
      source_type: "",
      tags: [],
      notes: "",
    });
  },
);

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return;
  saving.value = true;
  try {
    await createCustomer({
      ...form,
      country_code: form.country_code?.toUpperCase(),
      tags: form.tags,
    });
    ElMessage.success("客户创建成功");
    emit("update:modelValue", false);
    emit("created");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="新建客户"
    width="680px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <div class="form-grid">
        <el-form-item label="客户姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入客户姓名" />
        </el-form-item>
        <el-form-item label="公司名称" prop="company_name">
          <el-input v-model="form.company_name" placeholder="请输入公司名称" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="name@company.com" />
        </el-form-item>
        <el-form-item label="联系电话" prop="phone_e164">
          <el-input v-model="form.phone_e164" placeholder="+1 202 555 0100" />
        </el-form-item>
        <el-form-item label="国家代码" prop="country_code">
          <el-input v-model="form.country_code" maxlength="2" placeholder="US" />
        </el-form-item>
        <el-form-item label="语言" prop="language">
          <el-input v-model="form.language" placeholder="en-US" />
        </el-form-item>
        <el-form-item label="客户来源" prop="source_type">
          <el-input v-model="form.source_type" placeholder="website / whatsapp" />
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-select
            v-model="form.tags"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入后回车添加"
          />
        </el-form-item>
      </div>
      <el-form-item label="备注" prop="notes">
        <el-input v-model="form.notes" type="textarea" :rows="3" maxlength="5000" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">创建客户</el-button>
    </template>
  </el-dialog>
</template>
