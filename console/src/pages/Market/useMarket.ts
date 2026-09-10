import { useState, useCallback } from "react";
import { marketApi, Category, MarketSkill, MarketSkillDetail } from "../../api/modules/market";

export function useMarket(sourceId: string, isManager: boolean = true) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [skills, setSkills] = useState<MarketSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null);
  const [selectedBbkId, setSelectedBbkId] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<MarketSkillDetail | null>(null);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [publishModalOpen, setPublishModalOpen] = useState(false);

  const refreshCategories = useCallback(async () => {
    try {
      const data = await marketApi.listCategories(sourceId);
      setCategories(data);
    } catch (err) {
      console.error("Failed to load categories:", err);
    }
  }, [sourceId]);

  const refreshSkills = useCallback(async () => {
    setLoading(true);
    try {
      // 非管理员不传 bbkIds，由后端根据 X-Bbk-Id header 隐式过滤
      const bbkIdsToUse = isManager ? (selectedBbkId ?? undefined) : undefined;
      const data = await marketApi.listMarketSkills(
        sourceId,
        selectedCategory ?? undefined,
        bbkIdsToUse,
      );
      setSkills(data);
    } catch (err) {
      console.error("Failed to load skills:", err);
    } finally {
      setLoading(false);
    }
  }, [sourceId, selectedCategory, selectedBbkId, isManager]);

  // 刷新当前选中技能的详情
  const refreshSelectedSkill = useCallback(async () => {
    if (!selectedSkill) return;
    try {
      const detail = await marketApi.getSkillDetail(sourceId, selectedSkill.item_id);
      if (detail) {
        setSelectedSkill(detail);
      }
    } catch (err) {
      console.error("Failed to refresh skill detail:", err);
    }
  }, [sourceId, selectedSkill]);

  // 刷新技能列表和详情
  const refreshSkillsAndDetail = useCallback(async () => {
    await refreshSkills();
    await refreshSelectedSkill();
  }, [refreshSkills, refreshSelectedSkill]);

  const openSkillDetail = useCallback(
    async (itemId: string) => {
      try {
        const detail = await marketApi.getSkillDetail(sourceId, itemId);
        if (detail) {
          setSelectedSkill(detail);
          setDetailDrawerOpen(true);
        }
      } catch (err) {
        console.error("Failed to load skill detail:", err);
      }
    },
    [sourceId]
  );

  return {
    categories,
    skills,
    loading,
    selectedCategory,
    setSelectedCategory,
    selectedBbkId,
    setSelectedBbkId,
    selectedSkill,
    detailDrawerOpen,
    setDetailDrawerOpen,
    publishModalOpen,
    setPublishModalOpen,
    refreshCategories,
    refreshSkills,
    refreshSelectedSkill,
    refreshSkillsAndDetail,
    openSkillDetail,
  };
}
