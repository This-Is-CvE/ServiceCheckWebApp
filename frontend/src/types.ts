export type Light = "green" | "yellow" | "red" | "grey";
export type Answer = "yes" | "partial" | "no" | "na";

export interface User { id: number; username: string; full_name: string; role: "admin" | "consultant"; active: boolean }
export interface Customer { id: number; name: string; contact_name: string; contact_email: string; notes: string }
export interface Product { id: number; offer_id: number; name: string; description: string; green_min: number; yellow_min: number; parameter_count: number }
export interface Offer { id: number; name: string; description: string; products: Product[] }
export interface Parameter { id: number; product_id: number; category: string; name: string; description: string; weight: number; is_blocker: boolean; recommendation: string; position: number }
export interface TemplateItem { id: number; offer_id: number; section: Section; label: string; help: string; field_type: "text" | "textarea" | "date"; required: boolean; position: number }

export interface CheckListItem { id: number; title: string; customer_id: number; customer_name: string; offer_name: string; product_name: string; status: "draft" | "completed"; score: number | null; light: Light; created_at: string; completed_at: string | null }
export interface CheckItem { id: number; category: string; name: string; description: string; weight: number; is_blocker: boolean; recommendation: string; answer: Answer | null; comment: string }
export interface Finding { item_id: number; category: string; name: string; answer: Answer; weight: number; is_blocker: boolean; priority: "critical" | "high" | "medium" | "low"; recommendation: string; comment: string }
export interface CheckResult {
  score: number | null; light: Light; answered: number; total: number; complete: boolean;
  blocker_failed: string[]; blocker_partial: string[];
  categories: { name: string; score: number | null; answered: number; total: number }[];
  findings: Finding[];
}
export interface Check extends CheckListItem { system_description: string; green_min: number; yellow_min: number; created_by: string | null; items: CheckItem[]; result: CheckResult }

export type Section = "general" | "checklist" | "readiness";
export interface OnboardingListItem { id: number; title: string; customer_id: number; customer_name: string; offer_name: string; status: "open" | "completed"; progress: number; created_at: string }
export interface OnboardingItem { id: number; section: Section; label: string; help: string; field_type: "text" | "textarea" | "date"; required: boolean; value: string; done: boolean; comment: string }
export interface Asset { id: number; category: string; name: string; product_version: string; quantity: number; location: string; notes: string }
export interface Doc { id: number; filename: string; size: number; created_by: string; created_at: string }
export interface Onboarding extends OnboardingListItem { service_check_id: number | null; completed_at: string | null; items: OnboardingItem[]; assets: Asset[]; open_required: string[]; documents: Doc[] }

export const ANSWER_LABEL: Record<Answer, string> = { yes: "Erfüllt", partial: "Teilweise", no: "Nicht erfüllt", na: "n. a." };
export const LIGHT_LABEL: Record<Light, string> = { green: "Grün", yellow: "Gelb", red: "Rot", grey: "Offen" };
export const SECTION_LABEL: Record<Section, string> = {
  general: "Allgemeine Informationen",
  checklist: "Onboarding-Checkliste",
  readiness: "Voraussetzungen für die Serviceerbringung",
};
