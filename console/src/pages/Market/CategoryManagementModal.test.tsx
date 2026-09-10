import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CategoryManagementModal } from "./CategoryManagementModal";

const mocks = vi.hoisted(() => ({
  listCategories: vi.fn(),
  updateCategory: vi.fn(),
  createCategory: vi.fn(),
  deleteCategory: vi.fn(),
  reorderCategories: vi.fn(),
}));

vi.mock("../../api/modules/market", () => ({
  marketApi: mocks,
}));

const category = {
  id: 1,
  source_id: "source",
  name: "业务技能",
  sort_order: 0,
  branch_visible: true,
  skill_count: 3,
};

describe("CategoryManagementModal", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it("keeps category names read-only until one row enters edit mode", async () => {
    mocks.listCategories.mockResolvedValue([category]);

    render(
      <CategoryManagementModal
        open
        sourceId="source"
        onClose={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(mocks.listCategories).toHaveBeenCalledWith("source"),
    );
    await waitFor(() => expect(screen.getByText("业务技能")).toBeTruthy());
    expect(
      screen.queryByRole("textbox", { name: "分类名称 业务技能" }),
    ).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "编辑业务技能" }));

    const input = screen.getByRole("textbox", { name: "分类名称 业务技能" });
    expect((input as HTMLInputElement).value).toBe("业务技能");
    expect(screen.getByRole("button", { name: "保存业务技能" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "取消业务技能" })).toBeTruthy();
  });

  it("saves edited name and branch visibility together", async () => {
    mocks.listCategories.mockResolvedValue([category]);
    mocks.updateCategory.mockResolvedValue({
      ...category,
      name: "工具技能",
      branch_visible: false,
    });
    const onChanged = vi.fn();

    render(
      <CategoryManagementModal
        open
        sourceId="source"
        onClose={vi.fn()}
        onChanged={onChanged}
      />,
    );

    await waitFor(() => expect(screen.getByText("业务技能")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "编辑业务技能" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "分类名称 业务技能" }),
      {
        target: { value: "工具技能" },
      },
    );
    fireEvent.click(
      screen.getByRole("switch", { name: "设置业务技能分行可见性" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存业务技能" }));

    await waitFor(() =>
      expect(mocks.updateCategory).toHaveBeenCalledWith("source", 1, {
        name: "工具技能",
        branch_visible: false,
      }),
    );
    expect(onChanged).toHaveBeenCalled();
  });
});
