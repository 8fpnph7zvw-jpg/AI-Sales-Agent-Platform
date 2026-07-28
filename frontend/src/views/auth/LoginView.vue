<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Lock, Message, OfficeBuilding } from "@element-plus/icons-vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type { LoginRequest } from "@/types/auth";
import {
  readRememberedLogin,
  writeRememberedLogin,
} from "@/utils/auth-storage";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const formRef = ref<FormInstance>();
const submitting = ref(false);
const rememberedLogin = readRememberedLogin();
const rememberMe = ref(Boolean(rememberedLogin));
const form = reactive<LoginRequest>({
  tenant_slug: rememberedLogin?.tenantSlug ?? "",
  email: rememberedLogin?.email ?? "",
  password: "",
});
const rules: FormRules<LoginRequest> = {
  tenant_slug: [
    { required: true, message: "请输入企业标识", trigger: "blur" },
    { pattern: /^[a-z0-9-]+$/, message: "仅支持小写字母、数字和连字符", trigger: "blur" },
  ],
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" },
  ],
};

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return;
  submitting.value = true;
  try {
    await auth.login(form, rememberMe.value);
    writeRememberedLogin(
      rememberMe.value
        ? { tenantSlug: form.tenant_slug, email: form.email }
        : null,
    );
    ElMessage.success("登录成功");
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    await router.replace(redirect.startsWith("/") ? redirect : "/dashboard");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-story">
      <div class="login-story__brand"><span>AI</span> Sales Agent</div>
      <div class="login-story__content">
        <p class="eyebrow">ENTERPRISE INTELLIGENCE</p>
        <h1>把每一次询盘，<br />转化为可跟进的机会。</h1>
        <p>统一管理跨境客户、AI 会话、知识库、报价与自动化工作流。</p>
      </div>
      <div class="login-story__signal">
        <span class="signal-dot" />
        Secure cloud workspace
      </div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="login-card__heading">
          <p>欢迎回来</p>
          <h2>登录管理后台</h2>
          <span>使用企业账号访问您的销售工作台</span>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
          <el-form-item label="企业标识" prop="tenant_slug">
            <el-input v-model="form.tenant_slug" size="large" placeholder="company-slug">
              <template #prefix><el-icon><OfficeBuilding /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="form.email" size="large" autocomplete="username" placeholder="name@company.com">
              <template #prefix><el-icon><Message /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              show-password
              autocomplete="current-password"
              placeholder="请输入密码"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <div class="login-options">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
            <span>仅保存企业标识和邮箱，不保存密码</span>
          </div>
          <el-button type="primary" size="large" :loading="submitting" class="login-button" @click="submit">
            进入工作台
          </el-button>
        </el-form>
        <p class="login-card__security">账号权限由企业管理员统一配置</p>
      </div>
    </section>
  </div>
</template>
