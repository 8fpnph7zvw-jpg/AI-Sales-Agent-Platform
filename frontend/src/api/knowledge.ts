import { apiClient } from "./client";
import type { PageResult } from "@/types/api";
import type { KnowledgeFile } from "@/types/business";

export async function getKnowledgeFiles(params: {
  limit: number;
  offset: number;
  search?: string;
}): Promise<PageResult<KnowledgeFile>> {
  const { data } = await apiClient.get<PageResult<KnowledgeFile>>("/knowledge/files", { params });
  return data;
}

export async function uploadKnowledgeFile(
  file: File,
  collectionId?: string,
): Promise<KnowledgeFile> {
  const form = new FormData();
  form.append("file", file);
  if (collectionId) form.append("collection_id", collectionId);
  const { data } = await apiClient.post<KnowledgeFile>("/knowledge/files", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
