import { beforeEach, describe, expect, it } from 'vitest';
import { STORAGE_KEYS, storeViewVersionKey, loadViewVersionKey } from './storage';

describe('storage helpers', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores view version key by fixed key name', () => {
    storeViewVersionKey('v1.2.0');
    expect(localStorage.getItem(STORAGE_KEYS.viewVersionKey)).toBe('v1.2.0');
    expect(loadViewVersionKey()).toBe('v1.2.0');
  });
});
