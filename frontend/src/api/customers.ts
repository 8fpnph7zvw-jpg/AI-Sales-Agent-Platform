import { apiClient } from "./client";
import type { Customer, CustomerCreate, CustomerPage } from "@/types/business";

export interface CustomerQuery {
  limit: number;
  offset: number;
  search?: string;
  lifecycle_stage?: string;
}

export async function getCustomers(params: CustomerQuery): Promise<CustomerPage> {
  const { data } = await apiClient.get<CustomerPage>("/customers", { params });
  return data;
}

export async function createCustomer(payload: CustomerCreate): Promise<Customer> {
  const { data } = await apiClient.post<Customer>("/customers", payload);
  return data;
}
