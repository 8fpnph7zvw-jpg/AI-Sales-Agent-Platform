<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { DocumentAdd, Search, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage, type UploadFile } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { getKnowledgeFiles, uploadKnowledgeFile } from "@/api/knowledge";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type { KnowledgeFile } from "@/types/business";
import { formatBytes, formatDateTime } from "@/utils/format";

const loading = ref(false);
const uploading = ref(false);
const error = ref("");
const rows = ref<KnowledgeFile[]>([]);
const total = ref(0);
const uploadVisible = ref(false);
const pendingFile = ref<File | null>(null);
const collectionId = ref("");
const query = reactive({ page: 1, limit: 20, search: "" });

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const result = await getKnowledgeFiles({
      limit: query.limit,
      offset: (query.page - 1) * query.limit,
      search: query.search || undefined,
    });
    rows.value = result.data;
    total.value = result.total;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

function selectFile(uploadFile: UploadFile): void {
  pendingFile.value = uploadFile.raw ?? null;
}

async function upload(): Promise<void> {
  if (!pendingFile.value) {
    ElMessage.warning("请选择知识文件");
    return;
  }
  uploading.value = true;
  try {
    await uploadKnowledgeFile(pendingFile.value, collectionId.value || undefined);
    ElMessage.success("文件已提交，后台将进行解析和向量化");
    uploadVisible.value = false;
    pendingFile.value = null;
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    uploading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="知识库" description="管理供 Dify Agent 检索的企业知识文件">
      <el-button v-permission="'knowledge.upload'" type="primary" :icon="DocumentAdd" @click="uploadVisible = true">
        上传文件
      </el-button>
    </PageHeader>
    <el-card shadow="never" class="content-card">
      <div class="filter-bar">
        <el-input v-model="query.search" clearable :prefix-icon="Search" placeholder="搜索文件名或知识集合" @keyup.enter="load" />
        <el-button @click="load">查询</el-button>
      </div>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无知识文件" @retry="load">
        <el-table :data="rows">
          <el-table-column prop="filename" label="文件名" min-width="260" />
          <el-table-column prop="collection_name" label="知识集合" min-width="180" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }: { row: KnowledgeFile }">
              <el-tag :type="row.status === 'ready' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="chunk_count" label="分块数" width="100" />
          <el-table-column label="大小" width="110">
            <template #default="{ row }: { row: KnowledgeFile }">{{ formatBytes(row.size_bytes) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }: { row: KnowledgeFile }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>

    <el-dialog v-model="uploadVisible" title="上传知识文件" width="520px">
      <el-form label-position="top">
        <el-form-item label="知识集合 ID（可选）">
          <el-input v-model="collectionId" placeholder="目标知识集合 public_id" />
        </el-form-item>
        <el-upload drag :auto-upload="false" :limit="1" :on-change="selectFile" accept=".pdf,.doc,.docx,.txt,.md,.csv">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖放文件到这里，或<em>点击选择</em></div>
          <template #tip><div class="el-upload__tip">文件大小限制由服务端统一控制</div></template>
        </el-upload>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="upload">提交处理</el-button>
      </template>
    </el-dialog>
  </div>
</template>
