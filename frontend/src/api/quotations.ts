import { apiClient } from "./client";
import type { PageResult } from "@/types/api";
import type {
  Product,
  Quotation,
  QuotationCreate,
  QuotationStatus,
} from "@/types/business";

export async function getQuotations(params: {
  limit: number;
  offset: number;
  status?: string;
}): Promise<PageResult<Quotation>> {
  const { data } = await apiClient.get<PageResult<Quotation>>("/quotations", { params });
  return data;
}

export async function createQuotation(payload: QuotationCreate): Promise<Quotation> {
  const { data } = await apiClient.post<Quotation>("/quotation", payload);
  return data;
}

export async function updateQuotationStatus(
  quotationId: string,
  status: QuotationStatus,
): Promise<{ id: string; status: QuotationStatus }> {
  const { data } = await apiClient.patch<{ id: string; status: QuotationStatus }>(
    `/quotations/${quotationId}/status`,
    { status },
  );
  return data;
}

export async function deleteQuotation(quotationId: string): Promise<void> {
  await apiClient.delete(`/quotations/${quotationId}`);
}

export async function getProducts(params: {
  limit?: number;
  offset?: number;
} = {}): Promise<PageResult<Product>> {
  const { data } = await apiClient.get<PageResult<Product>>("/products", { params });
  return data;
}
