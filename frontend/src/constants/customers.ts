import type { Customer } from "@/types/business";

export const CUSTOMER_CATEGORY_PREFIX = "customer-category:";

export const customerCategoryOptions = [
  { value: "lead", label: "潜在客户", type: "info" },
  { value: "quoted", label: "已报价客户", type: "warning" },
  { value: "won", label: "已成交客户", type: "success" },
  { value: "vip", label: "VIP 客户", type: "danger" },
  { value: "follow_up", label: "待跟进客户", type: "primary" },
] as const;

export type CustomerCategory = (typeof customerCategoryOptions)[number]["value"];

const legacyCategoryMap: Record<string, CustomerCategory> = {
  new: "lead",
  qualified: "quoted",
  customer: "won",
};

export function getCustomerCategory(customer: Customer): CustomerCategory {
  const categoryTag = customer.tags.find((tag) => tag.startsWith(CUSTOMER_CATEGORY_PREFIX));
  const taggedValue = categoryTag?.slice(CUSTOMER_CATEGORY_PREFIX.length);
  if (customerCategoryOptions.some((option) => option.value === taggedValue)) {
    return taggedValue as CustomerCategory;
  }
  if (customerCategoryOptions.some((option) => option.value === customer.lifecycle_stage)) {
    return customer.lifecycle_stage as CustomerCategory;
  }
  return legacyCategoryMap[customer.lifecycle_stage] || "lead";
}

export function getCustomerCategoryOption(customer: Customer) {
  return customerCategoryOptions.find((option) => option.value === getCustomerCategory(customer))
    || customerCategoryOptions[0];
}

export function withCustomerCategory(tags: string[], category: CustomerCategory): string[] {
  return [
    ...tags.filter((tag) => !tag.startsWith(CUSTOMER_CATEGORY_PREFIX)),
    `${CUSTOMER_CATEGORY_PREFIX}${category}`,
  ];
}
