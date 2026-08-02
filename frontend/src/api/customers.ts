import { apiClient } from "./client";
import type {
  Customer,
  CustomerCreate,
  CustomerPage,
  CustomerUpdate,
} from "@/types/business";

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

export async function updateCustomer(
  customerId: string,
  payload: CustomerUpdate,
): Promise<Customer> {
  const { data } = await apiClient.patch<Customer>(`/customers/${customerId}`, payload);
  return data;
}

export async function deleteCustomer(customerId: string): Promise<void> {
  await apiClient.delete(`/customers/${customerId}`);
}

export async function assignCustomerOwner(
  customerId: string,
  ownerId: string | null,
): Promise<Customer> {
  const { data } = await apiClient.patch<Customer>(`/customers/${customerId}/owner`, {
    owner_id: ownerId,
  });
  return data;
}
