/** Resolve the detail route for a case/session record. */
export function caseDetailPath(caseData) {
  const id = caseData?.case_id || caseData?.session_id;
  if (!id) return '/';
  if (caseData?.is_mock) return `/cases/${id}`;
  return `/sessions/${id}`;
}

/** Whether a pathname is the active detail view for a case id. */
export function isCaseDetailActive(pathname, caseId, isMock) {
  if (!caseId) return false;
  if (isMock) return pathname === `/cases/${caseId}`;
  return pathname === `/sessions/${caseId}` || pathname === `/cases/${caseId}`;
}
