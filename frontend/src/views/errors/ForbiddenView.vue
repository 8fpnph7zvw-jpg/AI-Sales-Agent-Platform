<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <el-result
    icon="warning"
    title="没有访问权限"
    sub-title="当前账号没有访问此模块所需的权限，请联系企业管理员。"
  >
    <template #extra>
      <el-button type="primary" @click="router.push('/dashboard')">返回 Dashboard</el-button>
    </template>
  </el-result>
</template>
