import { request } from "../request";

export interface ToolGuardRule {
  id: string;
  tools: string[];
  params: string[];
  category: string;
  severity: string;
  patterns: string[];
  exclude_patterns: string[];
  description: string;
  remediation: string;
}

export interface ToolGuardConfig {
  enabled: boolean;
  guarded_tools: string[] | null;
  denied_tools: string[];
  custom_rules: ToolGuardRule[];
  disabled_rules: string[];
}

// ── File Guard types ──────────────────────────────────────────────

export interface FileGuardResponse {
  enabled: boolean;
  paths: string[];
}

export interface FileGuardUpdateBody {
  enabled?: boolean;
  paths?: string[];
}

// ── Skill Scanner types ────────────────────────────────────────────

export interface SkillScannerWhitelistEntry {
  skill_name: string;
  content_hash: string;
  added_at: string;
}

export type SkillScannerMode = "block" | "warn" | "off";

export interface SkillScannerConfig {
  mode: SkillScannerMode;
  timeout: number;
  whitelist: SkillScannerWhitelistEntry[];
}

export interface BlockedSkillFinding {
  severity: string;
  title: string;
  description: string;
  file_path: string;
  line_number: number | null;
  rule_id: string;
  analyzer?: string;
}

export interface BlockedSkillRecord {
  id: string;
  skill_name: string;
  blocked_at: string;
  max_severity: string;
  findings: BlockedSkillFinding[];
  content_hash: string;
  action: "blocked" | "warned";
  source_id?: string;
  user_id?: string;
  bbk_id?: string;
}

export interface BlockedSkillHistoryPage {
  items: BlockedSkillRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface SecurityScanErrorResponse {
  type: "security_scan_failed";
  detail: string;
  skill_name: string;
  max_severity: string;
  findings: BlockedSkillFinding[];
}

export const securityApi = {
  // ── Tool Guard ──────────────────────────────────────────────────

  getToolGuard: () => request<ToolGuardConfig>("/config/security/tool-guard"),

  updateToolGuard: (body: ToolGuardConfig) =>
    request<ToolGuardConfig>("/config/security/tool-guard", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getBuiltinRules: () =>
    request<ToolGuardRule[]>("/config/security/tool-guard/builtin-rules"),

  // ── File Guard ─────────────────────────────────────────────────

  getFileGuard: () => request<FileGuardResponse>("/config/security/file-guard"),

  updateFileGuard: (body: FileGuardUpdateBody) =>
    request<FileGuardResponse>("/config/security/file-guard", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // ── Skill Scanner ───────────────────────────────────────────────

  getSkillScanner: () =>
    request<SkillScannerConfig>("/config/security/skill-scanner"),

  updateSkillScanner: (body: SkillScannerConfig) =>
    request<SkillScannerConfig>("/config/security/skill-scanner", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getBlockedHistory: (page: number = 1, pageSize: number = 20) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return request<BlockedSkillHistoryPage>(
      `/config/security/skill-scanner/blocked-history?${params.toString()}`,
    );
  },

  getScanWarningCursor: async () => {
    const result = await request<{ cursor: string }>(
      "/config/security/skill-scanner/warning-cursor",
    );
    return result.cursor;
  },

  getLatestScanWarning: (skillName: string, since: string) => {
    const params = new URLSearchParams({ skill_name: skillName, since });
    return request<BlockedSkillRecord | null>(
      `/config/security/skill-scanner/blocked-history/latest-warning?${params.toString()}`,
    );
  },

  clearBlockedHistory: () =>
    request<{ cleared: boolean }>(
      "/config/security/skill-scanner/blocked-history",
      { method: "DELETE" },
    ),

  removeBlockedEntry: (recordId: string) =>
    request<{ removed: boolean }>(
      `/config/security/skill-scanner/blocked-history/${encodeURIComponent(
        recordId,
      )}`,
      { method: "DELETE" },
    ),

  addToWhitelist: (skillName: string, contentHash: string = "") =>
    request<{ whitelisted: boolean; skill_name: string }>(
      "/config/security/skill-scanner/whitelist",
      {
        method: "POST",
        body: JSON.stringify({
          skill_name: skillName,
          content_hash: contentHash,
        }),
      },
    ),

  removeFromWhitelist: (skillName: string) =>
    request<{ removed: boolean; skill_name: string }>(
      `/config/security/skill-scanner/whitelist/${encodeURIComponent(
        skillName,
      )}`,
      { method: "DELETE" },
    ),
};
