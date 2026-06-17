import { API_BASE_URL } from '../../config/env';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly responseText: string,
  ) {
    super(responseText);
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('hq_token');
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as T;
}

export async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const token = localStorage.getItem('hq_token');
  const headers = new Headers();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as T;
}
