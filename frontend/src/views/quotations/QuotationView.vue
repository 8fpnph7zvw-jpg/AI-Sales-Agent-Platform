<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Delete, Plus } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { getApiErrorMessage } from "@/api/client";
import { getCustomers } from "@/api/customers";
import { createQuotation, getProducts, getQuotations } from "@/api/quotations";
import ApiState from "@/components/common/ApiState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import type {
  Customer,
  Product,
  Quotation,
  QuotationCreate,
  QuotationItemInput,
} from "@/types/business";
import { formatDateTime, formatMoney } from "@/utils/format";

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const rows = ref<Quotation[]>([]);
const customers = ref<Customer[]>([]);
const products = ref<Product[]>([]);
const total = ref(0);
const drawerVisible = ref(false);
const query = reactive({ page: 1, limit: 20, status: "" });
const form = reactive<QuotationCreate>({
  customer_id: "",
  currency: "USD",
  shipping_amount: 0,
  items: [],
});

function newItem(): QuotationItemInput {
  return {
    sku: "",
    name: "",
    quantity: 1,
    unit: "pcs",
    unit_price: 0,
    discount_rate: 0,
    tax_rate: 0,
  };
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [result, productResult] = await Promise.all([
      getQuotations({
        limit: query.limit,
        offset: (query.page - 1) * query.limit,
        status: query.status || undefined,
      }),
      getProducts({ limit: 100, offset: 0 }),
    ]);
    rows.value = result.data;
    total.value = result.total;
    products.value = productResult.data;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError);
  } finally {
    loading.value = false;
  }
}

function applyProduct(item: QuotationItemInput): void {
  const product = products.value.find((candidate) => candidate.id === item.product_id);
  if (!product) return;
  item.sku = product.sku;
  item.name = product.name;
  item.description = product.description || undefined;
  item.unit = product.unit;
  item.unit_price = Number(product.base_price);
  item.quantity = Number(product.min_order_qty || 1);
}

async function openCreate(): Promise<void> {
  Object.assign(form, {
    customer_id: "",
    conversation_id: undefined,
    currency: "USD",
    valid_until: undefined,
    incoterm: "",
    payment_terms: "",
    notes: "",
    shipping_amount: 0,
    items: [newItem()],
  });
  drawerVisible.value = true;
  try {
    customers.value = (await getCustomers({ limit: 100, offset: 0 })).data;
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  }
}

async function submit(): Promise<void> {
  if (!form.customer_id || !form.items.length) {
    ElMessage.warning("请选择客户并添加至少一个报价项");
    return;
  }
  saving.value = true;
  try {
    await createQuotation({ ...form, items: form.items.map((item) => ({ ...item })) });
    ElMessage.success("报价单已创建");
    drawerVisible.value = false;
    await load();
  } catch (errorValue) {
    ElMessage.error(getApiErrorMessage(errorValue));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <PageHeader title="报价管理" description="集中管理销售报价及审批状态">
      <el-button v-permission="'quotation.create'" type="primary" :icon="Plus" @click="openCreate">创建报价</el-button>
    </PageHeader>
    <el-card shadow="never" class="content-card">
      <template #header>
        <div class="card-heading">
          <div>
            <strong>产品库</strong>
            <span>Demo 初始化产品，可直接用于创建报价</span>
          </div>
        </div>
      </template>
      <el-table :data="products" size="small">
        <el-table-column prop="sku" label="SKU" min-width="150" />
        <el-table-column prop="name" label="产品" min-width="200" />
        <el-table-column prop="category" label="分类" min-width="160" />
        <el-table-column label="基础价格" width="150">
          <template #default="{ row }: { row: Product }">
            {{ formatMoney(row.base_price, row.currency) }}
          </template>
        </el-table-column>
        <el-table-column prop="min_order_qty" label="MOQ" width="110" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="content-card">
      <div class="filter-bar">
        <el-select v-model="query.status" clearable placeholder="报价状态" @change="load">
          <el-option label="草稿" value="draft" />
          <el-option label="待审批" value="pending_approval" />
          <el-option label="已批准" value="approved" />
          <el-option label="已发送" value="sent" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
      <ApiState :loading="loading" :error="error" :empty="!rows.length" empty-text="暂无报价单" @retry="load">
        <el-table :data="rows">
          <el-table-column prop="quotation_no" label="报价单号" min-width="180" />
          <el-table-column label="客户" min-width="180">
            <template #default="{ row }: { row: Quotation }">{{ row.customer_name || row.customer_id }}</template>
          </el-table-column>
          <el-table-column label="金额" width="160">
            <template #default="{ row }: { row: Quotation }"><strong>{{ formatMoney(row.total_amount, row.currency) }}</strong></template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }: { row: Quotation }"><el-tag effect="plain">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="valid_until" label="有效期至" width="130" />
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }: { row: Quotation }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </ApiState>
    </el-card>

    <el-drawer v-model="drawerVisible" title="创建报价单" size="720px">
      <el-form :model="form" label-position="top">
        <div class="form-grid">
          <el-form-item label="客户" required>
            <el-select v-model="form.customer_id" filterable class="full-width">
              <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="币种" required><el-input v-model="form.currency" maxlength="3" /></el-form-item>
          <el-form-item label="有效期"><el-date-picker v-model="form.valid_until" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
          <el-form-item label="贸易术语"><el-input v-model="form.incoterm" placeholder="FOB / CIF" /></el-form-item>
          <el-form-item label="运费"><el-input-number v-model="form.shipping_amount" :min="0" :precision="2" class="full-width" /></el-form-item>
          <el-form-item label="付款条件"><el-input v-model="form.payment_terms" /></el-form-item>
        </div>
        <div class="section-heading"><strong>报价明细</strong><el-button text type="primary" :icon="Plus" @click="form.items.push(newItem())">添加项目</el-button></div>
        <div v-for="(item, index) in form.items" :key="index" class="quotation-item">
          <el-select
            v-model="item.product_id"
            filterable
            clearable
            placeholder="选择产品"
            @change="applyProduct(item)"
          >
            <el-option
              v-for="product in products"
              :key="product.id"
              :label="`${product.name} (${product.sku})`"
              :value="product.id"
            />
          </el-select>
          <el-input v-model="item.name" placeholder="产品名称" />
          <el-input-number v-model="item.quantity" :min="0.0001" :precision="2" />
          <el-input v-model="item.unit" placeholder="单位" />
          <el-input-number v-model="item.unit_price" :min="0" :precision="2" />
          <el-button :icon="Delete" circle text type="danger" @click="form.items.splice(index, 1)" />
        </div>
        <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">创建草稿</el-button>
      </template>
    </el-drawer>
  </div>
</template>
