import type { CaseStatus, IssueStatus, IssueStatusGroup } from './types';

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  not_run: '未测',
  passed: '通过',
  failed: '失败',
  blocked: '阻塞',
  skipped: '跳过',
};

export const CASE_STATUS_COLOR: Record<CaseStatus, string> = {
  not_run: 'default',
  passed: 'success',
  failed: 'error',
  blocked: 'warning',
  skipped: 'processing',
};

export const ISSUE_STATUS_LABEL: Record<IssueStatus, string> = {
  new: '新建',
  assigned: '已分派',
  fixing: '修复中',
  to_verify: '待验证',
  verify_failed: '验证失败',
  closed: '已关闭',
  rejected: '拒绝',
  duplicate: '重复',
  invalid: '已作废',
  deferred: '延期',
};

export const ISSUE_GROUP_LABEL: Record<IssueStatusGroup, string> = {
  all: '全部',
  open: '已开启',
  pending: '待闭环',
  closed: '已关闭',
  invalid: '已作废',
};

export const ISSUE_GROUP_STATUSES: Record<IssueStatusGroup, IssueStatus[]> = {
  all: [
    'new',
    'assigned',
    'fixing',
    'to_verify',
    'verify_failed',
    'closed',
    'rejected',
    'duplicate',
    'invalid',
    'deferred',
  ],
  open: ['new', 'assigned', 'fixing', 'verify_failed'],
  pending: ['to_verify'],
  closed: ['closed'],
  invalid: ['invalid', 'rejected', 'duplicate', 'deferred'],
};

export function getIssueStatusGroup(status: IssueStatus): IssueStatusGroup {
  if (ISSUE_GROUP_STATUSES.pending.includes(status)) {
    return 'pending';
  }
  if (ISSUE_GROUP_STATUSES.closed.includes(status)) {
    return 'closed';
  }
  if (ISSUE_GROUP_STATUSES.invalid.includes(status)) {
    return 'invalid';
  }
  return 'open';
}

export function statusMatchesGroup(status: IssueStatus, group: IssueStatusGroup): boolean {
  if (group === 'all') {
    return true;
  }
  return ISSUE_GROUP_STATUSES[group].includes(status);
}
