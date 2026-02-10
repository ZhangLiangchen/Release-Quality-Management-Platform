import type { Repository } from './repository';
import { HttpRepository } from './http/httpRepository';
import { MockRepository } from './mock/mockRepository';

const dataSource = import.meta.env.VITE_DATA_SOURCE ?? 'mock';
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const repository: Repository =
  dataSource === 'api' ? new HttpRepository(apiBaseUrl) : new MockRepository();

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
