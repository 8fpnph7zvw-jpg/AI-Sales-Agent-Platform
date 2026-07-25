export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string | null;
  };
  detail?: string | Array<{ loc: Array<string | number>; msg: string }>;
}

export interface PageResult<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}
