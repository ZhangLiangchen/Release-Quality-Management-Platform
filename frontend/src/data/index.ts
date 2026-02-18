import type { Repository } from './repository';
import { HttpRepository } from './http/httpRepository';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const repository: Repository = new HttpRepository(apiBaseUrl);

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
