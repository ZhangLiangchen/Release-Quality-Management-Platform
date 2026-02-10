import { describe, expect, it } from 'vitest';
import type { CaseWithStatus, Issue } from '../domain/types';
import { calculateDashboardKpi } from './metrics';

const cases: CaseWithStatus[] = [
  {
    caseId: 'C1',
    caseKey: 'TC-1',
    title: 'A',
    steps: 'S',
    expected: 'E',
    module: 'M',
    tags: [],
    status: 'active',
    latestStatus: 'passed',
  },
  {
    caseId: 'C2',
    caseKey: 'TC-2',
    title: 'B',
    steps: 'S',
    expected: 'E',
    module: 'M',
    tags: [],
    status: 'active',
    latestStatus: 'failed',
  },
  {
    caseId: 'C3',
    caseKey: 'TC-3',
    title: 'C',
    steps: 'S',
    expected: 'E',
    module: 'M',
    tags: [],
    status: 'active',
    latestStatus: 'skipped',
  },
];

const issues: Issue[] = [
  {
    issueId: 'I1',
    issueKey: 'ISS-1',
    title: 'Issue 1',
    description: '',
    status: 'to_verify',
    priority: 'high',
    severity: 'major',
    reporterId: 'U1',
    reporterName: 'qa',
    foundVersionKey: 'v1',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    links: [],
  },
  {
    issueId: 'I2',
    issueKey: 'ISS-2',
    title: 'Issue 2',
    description: '',
    status: 'closed',
    priority: 'high',
    severity: 'major',
    reporterId: 'U1',
    reporterName: 'qa',
    foundVersionKey: 'v1',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    links: [],
  },
];

describe('calculateDashboardKpi', () => {
  it('calculates rates by PRD rules', () => {
    const result = calculateDashboardKpi(cases, issues, 'v1');

    expect(result.totalCases).toBe(3);
    expect(result.executedCases).toBe(3);
    expect(result.executionRate).toBeCloseTo(1);
    expect(result.passRate).toBeCloseTo(0.5);
    expect(result.resolvedIssues).toBe(1);
    expect(result.pendingIssueCount).toBe(1);
  });
});
