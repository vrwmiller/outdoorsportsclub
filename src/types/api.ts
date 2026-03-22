// API response types — filled in as endpoints are implemented in Phase 2.

export interface MemberProfile {
  memberId: string;
  memberNum: string;
  email: string;
  trainingLevel: number;
  duesPaidUntil: string | null;
  waiverSignedAt: string | null;
}
