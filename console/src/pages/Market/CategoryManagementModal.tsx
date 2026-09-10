import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Tag,
  Tooltip,
  message,
} from "antd";
import {
  DeleteOutlined,
  HolderOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { marketApi, type Category } from "../../api/modules/market";

interface CategoryManagementModalProps {
  open: boolean;
  sourceId: string;
  onClose: () => void;
  onChanged: () => Promise<void> | void;
}

function getErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "操作失败";
  try {
    const payload = JSON.parse(error.message);
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) {
      return `${detail.message}${detail.skill_count ? `（当前 ${detail.skill_count} 个技能）` : ""}`;
    }
  } catch {
    // Keep the original message for non-JSON API errors.
  }
  return error.message || "操作失败";
}

export function CategoryManagementModal({
  open,
  sourceId,
  onClose,
  onChanged,
}: CategoryManagementModalProps) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingOrder, setSavingOrder] = useState(false);
  const [newName, setNewName] = useState("");
  const [draggedId, setDraggedId] = useState<number | null>(null);

  const loadCategories = useCallback(async () => {
    setLoading(true);
    try {
      setCategories(await marketApi.listCategories(sourceId));
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => {
    if (open) void loadCategories();
  }, [loadCategories, open]);

  const addCategory = async () => {
    const name = newName.trim();
    if (!name) {
      message.warning("请输入分类名称");
      return;
    }
    try {
      await marketApi.createCategory(sourceId, name);
      setNewName("");
      await loadCategories();
      await onChanged();
      message.success("分类已新增");
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const updateCategory = async (
    category: Category,
    data: { name?: string; branch_visible?: boolean },
  ) => {
    try {
      const updated = await marketApi.updateCategory(sourceId, category.id, data);
      setCategories((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      await onChanged();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const deleteCategory = async (category: Category) => {
    try {
      await marketApi.deleteCategory(sourceId, category.id);
      setCategories((current) => current.filter((item) => item.id !== category.id));
      await onChanged();
      message.success("分类已删除");
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleDrop = (targetId: number) => {
    if (draggedId === null || draggedId === targetId) return;
    setCategories((current) => {
      const next = [...current];
      const from = next.findIndex((item) => item.id === draggedId);
      const to = next.findIndex((item) => item.id === targetId);
      if (from < 0 || to < 0) return current;
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
    setDraggedId(null);
  };

  const saveOrder = async () => {
    setSavingOrder(true);
    try {
      await marketApi.reorderCategories(
        sourceId,
        categories.map((category) => category.id),
      );
      await onChanged();
      message.success("排序已保存");
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSavingOrder(false);
    }
  };

  return (
    <Modal
      title="分类管理"
      open={open}
      onCancel={onClose}
      footer={null}
      width={800}
      destroyOnHidden
    >
      <div style={{ color: "#4b5563", fontSize: 13, marginBottom: 16 }}>
        仅技能使用此分类体系。分类关闭分行可见后，分行用户将不会看到该分类及其技能；总行仍可见。
      </div>
      <Alert
        type="info"
        showIcon
        message="删除分类前请先将其中技能调整到其他分类。非空分类不能删除。"
        style={{ marginBottom: 16 }}
      />
      <Space.Compact style={{ width: "100%", marginBottom: 16 }}>
        <Input
          aria-label="新分类名称"
          placeholder="输入新分类名称"
          value={newName}
          maxLength={128}
          onChange={(event) => setNewName(event.target.value)}
          onPressEnter={() => void addCategory()}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void addCategory()}>
          新增分类
        </Button>
      </Space.Compact>

      <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "32px minmax(0, 1fr) 100px 150px 72px",
            gap: 12,
            padding: "10px 16px",
            background: "#f7f9fc",
            color: "#8a94a6",
            fontSize: 12,
          }}
        >
          <span />
          <span>分类名称</span>
          <span>技能数量</span>
          <span>分行可见</span>
          <span>操作</span>
        </div>
        {loading ? (
          <div style={{ padding: 36, textAlign: "center", color: "#8a94a6" }}>加载中...</div>
        ) : categories.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无分类" style={{ padding: 24 }} />
        ) : (
          categories.map((category) => (
            <div
              key={category.id}
              draggable
              onDragStart={() => setDraggedId(category.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => handleDrop(category.id)}
              style={{
                display: "grid",
                gridTemplateColumns: "32px minmax(0, 1fr) 100px 150px 72px",
                gap: 12,
                alignItems: "center",
                padding: "12px 16px",
                borderTop: "1px solid #eef0f3",
                background: draggedId === category.id ? "#eef4ff" : "#fff",
              }}
            >
              <Tooltip title="拖动调整顺序">
                <HolderOutlined
                  aria-label={`拖动${category.name}`}
                  style={{ color: "#8a94a6", cursor: "grab" }}
                />
              </Tooltip>
              <Input
                aria-label={`分类名称 ${category.name}`}
                defaultValue={category.name}
                maxLength={128}
                onBlur={(event) => {
                  const name = event.target.value.trim();
                  if (name && name !== category.name) {
                    void updateCategory(category, { name });
                  }
                }}
                onPressEnter={(event) => event.currentTarget.blur()}
              />
              <Tag style={{ width: "fit-content", margin: 0 }}>{category.skill_count ?? 0}</Tag>
              <Switch
                checked={category.branch_visible}
                checkedChildren="分行可见"
                unCheckedChildren="仅总行"
                onChange={(checked) =>
                  void updateCategory(category, { branch_visible: checked })
                }
              />
              <Popconfirm
                title={`删除分类“${category.name}”？`}
                description={
                  category.skill_count > 0
                    ? `当前有 ${category.skill_count} 个技能，删除前请先调整技能分类。`
                    : "此操作不可恢复。"
                }
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true, disabled: category.skill_count > 0 }}
                onConfirm={() => void deleteCategory(category)}
              >
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label={`删除${category.name}`}
                />
              </Popconfirm>
            </div>
          ))
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={savingOrder}
          disabled={categories.length < 2}
          onClick={() => void saveOrder()}
        >
          保存排序
        </Button>
      </div>
    </Modal>
  );
}
