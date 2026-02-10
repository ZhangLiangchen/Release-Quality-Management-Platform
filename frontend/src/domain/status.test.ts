import { describe, expect, it } from 'vitest';
import { getIssueStatusGroup, statusMatchesGroup } from './status';

describe('issue status mapping', () => {
  it('maps to pending group', () => {
    expect(getIssueStatusGroup('to_verify')).toBe('pending');
  });

  it('maps to invalid group', () => {
    expect(getIssueStatusGroup('duplicate')).toBe('invalid');
  });

  it('checks group filter correctly', () => {
    expect(statusMatchesGroup('assigned', 'open')).toBe(true);
    expect(statusMatchesGroup('closed', 'open')).toBe(false);
  });
});
