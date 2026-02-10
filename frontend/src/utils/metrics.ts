import type { CaseWithStatus, DashboardKpi, Issue } from '../domain/types';
import { getIssueStatusGroup } from '../domain/status';

const EXECUTED_STATUSES = new Set(['passed', 'failed', 'blocked', 'skipped']);

export function calculateDashboardKpi(cases: CaseWithStatus[], issues: Issue[], versionKey: string): DashboardKpi {
  const totalCases = cases.length;
  const executedCases = cases.filter((item) => EXECUTED_STATUSES.has(item.latestStatus)).length;
  const passedCases = cases.filter((item) => item.latestStatus === 'passed').length;
  const skippedCases = cases.filter((item) => item.latestStatus === 'skipped').length;
  const executionRate = totalCases === 0 ? 0 : executedCases / totalCases;

  const validExecuted = executedCases - skippedCases;
  const passRate = validExecuted <= 0 ? null : passedCases / validExecuted;

  const versionIssues = issues.filter((item) => item.foundVersionKey === versionKey);
  const totalIssues = versionIssues.length;
  const resolvedIssues = versionIssues.filter((item) => {
    const group = getIssueStatusGroup(item.status);
    return group === 'closed' || group === 'invalid';
  }).length;
  const pendingIssueCount = versionIssues.filter((item) => getIssueStatusGroup(item.status) === 'pending').length;
  const resolutionRate = totalIssues === 0 ? 0 : resolvedIssues / totalIssues;

  return {
    totalCases,
    executedCases,
    passedCases,
    skippedCases,
    executionRate,
    passRate,
    totalIssues,
    resolvedIssues,
    resolutionRate,
    pendingIssueCount,
  };
}

export function formatRate(rate: number | null): string {
  if (rate === null) {
    return 'N/A';
  }
  return `${(rate * 100).toFixed(1)}%`;
}
