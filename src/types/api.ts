// API response types — filled in as endpoints are implemented.

/** Response shape of GET /v1/members/me */
export interface MemberProfile {
  member_num: string;
  training_level: number;
  service_hours: string;
  dues_paid_until: string | null;
  waiver_signed_at: string | null;
  mobile_phone: string | null;
  annual_dues_cents: number | null;
}
