<script setup lang="ts">
import { WarningFilled } from "@element-plus/icons-vue";

defineProps<{
  loading?: boolean;
  error?: string;
  empty?: boolean;
  emptyText?: string;
}>();

defineEmits<{
  retry: [];
}>();
</script>

<template>
  <div v-loading="loading" class="api-state">
    <el-result
      v-if="error && !loading"
      icon="warning"
      title="数据加载失败"
      :sub-title="error"
    >
      <template #icon>
        <el-icon class="api-state__warning"><WarningFilled /></el-icon>
      </template>
      <template #extra>
        <el-button type="primary" @click="$emit('retry')">重新加载</el-button>
      </template>
    </el-result>
    <el-empty v-else-if="empty && !loading" :description="emptyText || '暂无数据'" />
    <slot v-else />
  </div>
</template>
