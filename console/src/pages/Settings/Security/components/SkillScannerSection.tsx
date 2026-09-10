import { useState, useCallback } from "react";
import {
  Card,
  InputNumber,
  Table,
  Tag,
  Button,
  Modal,
  Tooltip,
  Empty,
  Tabs,
  Alert,
} from "@agentscope-ai/design";
import { useAppMessage } from "../../../../hooks/useAppMessage";
import { Select, Space } from "antd";
import { Trash2, ShieldCheck, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSkillScanner } from "../useSkillScanner";
import type {
  BlockedSkillRecord,
  BlockedSkillFinding,
  SkillScannerWhitelistEntry,
  SkillScannerMode,
} from "../../../../api/modules/security";
import { mySkillsApi } from "../../../../api/modules/mySkills";
import { useTheme } from "../../../../contexts/ThemeContext";
import styles from "../index.module.less";

function FindingsModal({
  findings,
  skillName,
  open,
  onClose,
}: {
  findings: BlockedSkillFinding[];
  skillName: string;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Modal
      title={`${t(
        "security.skillScanner.scanAlerts.viewFindings",
      )} - ${skillName}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={700}
    >
      <Table
        dataSource={findings}
        rowKey={(_, idx) => String(idx)}
        pagination={false}
        size="small"
        columns={[
          {
            title: "Title",
            dataIndex: "title",
            key: "title",
            width: 200,
          },
          {
            title: "File",
            key: "location",
            width: 160,
            render: (_: unknown, record: BlockedSkillFinding) =>
              record.line_number
                ? `${record.file_path}:${record.line_number}`
                : record.file_path,
          },
          {
            title: t("security.skillScanner.scanAlerts.analyzer"),
            dataIndex: "analyzer",
            key: "analyzer",
            width: 120,
            render: (value: string | undefined) => value || "-",
          },
          {
            title: "Description",
            dataIndex: "description",
            key: "description",
            ellipsis: true,
          },
        ]}
      />
    </Modal>
  );
}

export function SkillScannerSection() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const darkBtnStyle = isDark ? { color: "rgba(255,255,255,0.75)" } : undefined;
  const {
    config,
    blockedHistory,
    whitelist,
    loading,
    historyLoading,
    historyMutating,
    historyError,
    historyPage,
    historyPageSize,
    historyTotal,
    updateConfig,
    addToWhitelist,
    removeFromWhitelist,
    removeBlockedEntry,
    clearBlockedHistory,
    fetchBlockedHistory,
    setHistoryPagination,
  } = useSkillScanner();

  const { message } = useAppMessage();
  const [saving, setSaving] = useState(false);
  const [findingsModal, setFindingsModal] = useState<{
    open: boolean;
    findings: BlockedSkillFinding[];
    skillName: string;
  }>({ open: false, findings: [], skillName: "" });

  const handleModeChange = useCallback(
    async (mode: SkillScannerMode) => {
      setSaving(true);
      const ok = await updateConfig({ mode });
      if (ok) message.success(t("security.skillScanner.saveSuccess"));
      else message.error(t("security.skillScanner.saveFailed"));
      setSaving(false);
    },
    [message, updateConfig, t],
  );

  const [pendingTimeout, setPendingTimeout] = useState<number | null>(null);

  const handleTimeoutBlur = useCallback(async () => {
    const value = pendingTimeout;
    if (value === null || value < 5 || value > 300) {
      setPendingTimeout(null);
      return;
    }
    setSaving(true);
    const ok = await updateConfig({ timeout: value });
    if (ok) message.success(t("security.skillScanner.saveSuccess"));
    else message.error(t("security.skillScanner.saveFailed"));
    setPendingTimeout(null);
    setSaving(false);
  }, [message, pendingTimeout, updateConfig, t]);

  const handleAllowSkill = useCallback(
    async (record: BlockedSkillRecord) => {
      const ok = await addToWhitelist(record.skill_name, record.content_hash);
      if (ok) {
        message.success(t("security.skillScanner.whitelist.addSuccess"));
        const removed = await removeBlockedEntry(record.id);
        if (!removed) {
          message.error(t("security.skillScanner.scanAlerts.removeFailed"));
        }
      } else {
        message.error(t("security.skillScanner.whitelist.addFailed"));
      }
    },
    [addToWhitelist, message, removeBlockedEntry, t],
  );

  const handleRemoveBlockedEntry = useCallback(
    async (recordId: string) => {
      const ok = await removeBlockedEntry(recordId);
      if (ok) {
        message.success(t("security.skillScanner.scanAlerts.removeSuccess"));
      } else {
        message.error(t("security.skillScanner.scanAlerts.removeFailed"));
      }
    },
    [message, removeBlockedEntry, t],
  );

  const handleRemoveWhitelist = useCallback(
    async (skillName: string) => {
      Modal.confirm({
        title: t("security.skillScanner.whitelist.removeConfirm"),
        content: t("security.skillScanner.whitelist.removeWillDisable"),
        onOk: async () => {
          const ok = await removeFromWhitelist(skillName);
          if (!ok) {
            message.error(t("security.skillScanner.whitelist.removeFailed"));
            return;
          }
          try {
            await mySkillsApi.disableSkill(skillName);
            message.success(
              t("security.skillScanner.whitelist.removeAndDisabled"),
            );
          } catch {
            message.success(t("security.skillScanner.whitelist.removeSuccess"));
          }
        },
      });
    },
    [message, removeFromWhitelist, t],
  );

  const handleClearHistory = useCallback(() => {
    Modal.confirm({
      title: t("security.skillScanner.scanAlerts.clearConfirm"),
      onOk: async () => {
        const ok = await clearBlockedHistory();
        if (ok) {
          message.success(t("security.skillScanner.scanAlerts.clearSuccess"));
        } else {
          message.error(t("security.skillScanner.scanAlerts.clearFailed"));
        }
      },
    });
  }, [clearBlockedHistory, message, t]);

  if (loading || !config) return null;

  const enabled = config.mode !== "off";

  const blockedColumns = [
    {
      title: t("security.skillScanner.scanAlerts.skillName"),
      dataIndex: "skill_name",
      key: "skill_name",
      width: 180,
    },
    {
      title: t("security.skillScanner.scanAlerts.user"),
      dataIndex: "user_id",
      key: "user_id",
      width: 120,
      render: (value: string | undefined) => value || "-",
    },
    {
      title: t("security.skillScanner.scanAlerts.branch"),
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 120,
      render: (value: string | undefined) => value || "-",
    },
    {
      title: t("security.skillScanner.scanAlerts.action"),
      dataIndex: "action",
      key: "action",
      width: 100,
      render: (action: string) => (
        <Tag color={action === "blocked" ? "red" : "orange"}>
          {action === "blocked"
            ? t("security.skillScanner.scanAlerts.actionBlocked")
            : t("security.skillScanner.scanAlerts.actionWarned")}
        </Tag>
      ),
    },
    {
      title: t("security.skillScanner.scanAlerts.time"),
      dataIndex: "blocked_at",
      key: "blocked_at",
      width: 180,
      render: (val: string) => {
        try {
          return new Date(val).toLocaleString();
        } catch {
          return val;
        }
      },
    },
    {
      title: t("security.skillScanner.scanAlerts.actions"),
      key: "actions",
      width: 200,
      render: (_: unknown, record: BlockedSkillRecord) => (
        <Space size="small">
          <Tooltip title={t("security.skillScanner.scanAlerts.viewFindings")}>
            <Button
              aria-label={t("security.skillScanner.scanAlerts.viewFindings")}
              type="text"
              size="middle"
              style={darkBtnStyle}
              onClick={() =>
                setFindingsModal({
                  open: true,
                  findings: record.findings,
                  skillName: record.skill_name,
                })
              }
            >
              <Eye size={14} />
            </Button>
          </Tooltip>
          <Tooltip title={t("security.skillScanner.scanAlerts.allowSkill")}>
            <Button
              aria-label={t("security.skillScanner.scanAlerts.allowSkill")}
              type="text"
              size="middle"
              style={darkBtnStyle}
              disabled={historyMutating}
              onClick={() => handleAllowSkill(record)}
            >
              <ShieldCheck size={14} />
            </Button>
          </Tooltip>
          <Tooltip title={t("security.skillScanner.scanAlerts.remove")}>
            <Button
              aria-label={t("security.skillScanner.scanAlerts.remove")}
              type="text"
              size="middle"
              danger
              disabled={historyMutating}
              onClick={() => handleRemoveBlockedEntry(record.id)}
            >
              <Trash2 size={14} />
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const whitelistColumns = [
    {
      title: t("security.skillScanner.whitelist.skillName"),
      dataIndex: "skill_name",
      key: "skill_name",
      width: 200,
    },
    {
      title: t("security.skillScanner.whitelist.contentHash"),
      dataIndex: "content_hash",
      key: "content_hash",
      width: 200,
      ellipsis: true,
      render: (hash: string) =>
        hash ? (
          <Tooltip title={hash}>
            <code className={styles.codeHash}>{hash.substring(0, 16)}...</code>
          </Tooltip>
        ) : (
          <span style={{ color: "#999" }}>any</span>
        ),
    },
    {
      title: t("security.skillScanner.whitelist.addedAt"),
      dataIndex: "added_at",
      key: "added_at",
      width: 180,
      render: (val: string) => {
        try {
          return new Date(val).toLocaleString();
        } catch {
          return val;
        }
      },
    },
    {
      title: t("security.skillScanner.whitelist.actions"),
      key: "actions",
      width: 100,
      render: (_: unknown, record: SkillScannerWhitelistEntry) => (
        <Tooltip title={t("security.skillScanner.whitelist.remove")}>
          <Button
            type="text"
            size="middle"
            danger
            onClick={() => handleRemoveWhitelist(record.skill_name)}
          >
            <Trash2 size={14} />
          </Button>
        </Tooltip>
      ),
    },
  ];

  return (
    <>
      <Card className={styles.formCard}>
        <div className={styles.skillScannerConfig}>
          <div className={styles.skillScannerConfigItem}>
            <Tooltip title={t("security.skillScanner.modeTooltip")}>
              <span className={styles.skillScannerLabel}>
                {t("security.skillScanner.mode")}
              </span>
            </Tooltip>
            <Select
              value={config.mode}
              onChange={handleModeChange}
              disabled={saving}
              style={{ width: 140 }}
              options={[
                {
                  value: "block",
                  label: t("security.skillScanner.modeBlock"),
                },
                { value: "warn", label: t("security.skillScanner.modeWarn") },
                { value: "off", label: t("security.skillScanner.modeOff") },
              ]}
            />
          </div>

          <div className={styles.skillScannerConfigItem}>
            <Tooltip title={t("security.skillScanner.timeoutTooltip")}>
              <span className={styles.skillScannerLabel}>
                {t("security.skillScanner.timeout")}
              </span>
            </Tooltip>
            <InputNumber
              min={5}
              max={300}
              value={pendingTimeout ?? config.timeout}
              onChange={(v) => setPendingTimeout(v)}
              onBlur={handleTimeoutBlur}
              onPressEnter={handleTimeoutBlur}
              disabled={!enabled}
              style={{ width: 100 }}
            />
          </div>
        </div>
      </Card>

      <Tabs
        className={styles.innerTabs}
        items={[
          {
            key: "scanAlerts",
            label: (
              <span>
                {t("security.skillScanner.scanAlerts.title")}
                {historyTotal > 0 && (
                  <span className={styles.tabBadge}>{historyTotal}</span>
                )}
              </span>
            ),
            children: (
              <div className={styles.tabPanelContent}>
                {historyTotal > 0 && (
                  <div className={styles.tabPanelHeader}>
                    <Button
                      aria-label={t(
                        "security.skillScanner.scanAlerts.clearAll",
                      )}
                      size="small"
                      danger
                      loading={historyMutating}
                      disabled={historyMutating}
                      onClick={handleClearHistory}
                    >
                      {t("security.skillScanner.scanAlerts.clearAll")}
                    </Button>
                  </div>
                )}
                <Card className={styles.tableCard}>
                  {historyError ? (
                    <Alert
                      type="error"
                      showIcon
                      message={t("security.skillScanner.scanAlerts.loadFailed")}
                      action={
                        <Button size="small" onClick={fetchBlockedHistory}>
                          {t("security.skillScanner.scanAlerts.retry")}
                        </Button>
                      }
                    />
                  ) : blockedHistory.length === 0 &&
                    !historyLoading &&
                    historyTotal === 0 ? (
                    <div className={styles.emptyState}>
                      <Empty
                        description={
                          <span className={styles.emptyText}>
                            {t("security.skillScanner.scanAlerts.empty")}
                          </span>
                        }
                      />
                    </div>
                  ) : (
                    <Table
                      dataSource={blockedHistory}
                      columns={blockedColumns}
                      rowKey="id"
                      loading={historyLoading}
                      pagination={{
                        current: historyPage,
                        pageSize: historyPageSize,
                        total: historyTotal,
                        showSizeChanger: true,
                        pageSizeOptions: ["10", "20", "50", "100"],
                        onChange: setHistoryPagination,
                      }}
                      size="small"
                    />
                  )}
                </Card>
              </div>
            ),
          },
          {
            key: "whitelist",
            label: (
              <span>
                {t("security.skillScanner.whitelist.title")}
                {whitelist.length > 0 && (
                  <span className={styles.tabBadge}>{whitelist.length}</span>
                )}
              </span>
            ),
            children: (
              <div className={styles.tabPanelContent}>
                <Card className={styles.tableCard}>
                  {whitelist.length === 0 ? (
                    <div className={styles.emptyState}>
                      <Empty
                        description={
                          <span className={styles.emptyText}>
                            {t("security.skillScanner.whitelist.empty")}
                          </span>
                        }
                      />
                    </div>
                  ) : (
                    <Table
                      dataSource={whitelist}
                      columns={whitelistColumns}
                      rowKey="skill_name"
                      pagination={{
                        defaultPageSize: 20,
                        showSizeChanger: true,
                        pageSizeOptions: ["20", "50", "100"],
                      }}
                      size="small"
                    />
                  )}
                </Card>
              </div>
            ),
          },
        ]}
      />

      <FindingsModal
        findings={findingsModal.findings}
        skillName={findingsModal.skillName}
        open={findingsModal.open}
        onClose={() =>
          setFindingsModal({ open: false, findings: [], skillName: "" })
        }
      />
    </>
  );
}
