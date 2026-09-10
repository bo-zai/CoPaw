import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { request } from "../request";
import { wplusSopApi } from "./wplusSop";

vi.mock("../request", () => ({
  request: vi.fn(),
}));

vi.mock("../config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

vi.mock("../authHeaders", () => ({
  buildAuthHeaders: () => ({ Authorization: "Bearer test" }),
}));

describe("wplusSopApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("confirms an entry proposal with a stable request id", async () => {
    vi.mocked(request).mockResolvedValue({ accepted: true });

    await wplusSopApi.confirmEntry("proposal/1", "cmd-entry");

    expect(request).toHaveBeenCalledWith(
      "/wplus-sop/entry-proposals/proposal%2F1/confirm",
      {
        method: "POST",
        body: JSON.stringify({ command_request_id: "cmd-entry" }),
        signal: undefined,
      },
    );
  });

  it("rejects an entry proposal before replaying it in Chat", async () => {
    vi.mocked(request).mockResolvedValue({ status: "rejected" });

    await wplusSopApi.rejectEntry("proposal-1", "cmd-reject");

    expect(request).toHaveBeenCalledWith(
      "/wplus-sop/entry-proposals/proposal-1/reject",
      {
        method: "POST",
        body: JSON.stringify({ command_request_id: "cmd-reject" }),
        signal: undefined,
      },
    );
  });

  it("loads the authoritative session projection", async () => {
    vi.mocked(request).mockResolvedValue({ session_id: "sop-1" });

    await wplusSopApi.getSession("sop-1");

    expect(request).toHaveBeenCalledWith(
      "/wplus-sop/sessions/sop-1",
      expect.objectContaining({ signal: undefined }),
    );
  });

  it("posts one discriminated command with its stable request id", async () => {
    const command = {
      command: "accept_trial" as const,
      command_request_id: "cmd-stable",
      expected_state_version: 9,
    };
    vi.mocked(request).mockResolvedValue({ accepted: true });

    await wplusSopApi.sendCommand("sop-1", command);

    expect(request).toHaveBeenCalledWith("/wplus-sop/sessions/sop-1/commands", {
      method: "POST",
      body: JSON.stringify(command),
      signal: undefined,
    });
  });

  it("downloads an authenticated generated artifact", async () => {
    const blob = new Blob(["# SOP"], { type: "text/markdown" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(blob),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      wplusSopApi.downloadArtifact("sop/1", "render/md"),
    ).resolves.toBe(blob);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/wplus-sop/sessions/sop%2F1/artifacts/render%2Fmd?download=true",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer test" },
      }),
    );
  });

  it("reads final, stage report, and cumulative artifacts with full identity", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue("artifact body"),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      wplusSopApi.readArtifact("sop/1", "render/html"),
    ).resolves.toBe("artifact body");
    await expect(
      wplusSopApi.readStageReportArtifact("sop/1", {
        stageId: "stage/一",
        revision: 3,
        reportNo: 2,
        artifactId: "stage/html",
      }),
    ).resolves.toBe("artifact body");
    await expect(
      wplusSopApi.readCumulativeArtifact("sop/1", {
        previewVersion: 4,
        artifactId: "cumulative/html",
      }),
    ).resolves.toBe("artifact body");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/wplus-sop/sessions/sop%2F1/artifacts/render%2Fhtml",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer test" },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/wplus-sop/sessions/sop%2F1/stage-report-artifacts/stage%2Fhtml?stage_id=stage%2F%E4%B8%80&revision=3&report_no=2",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer test" },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/wplus-sop/sessions/sop%2F1/cumulative-artifacts/cumulative%2Fhtml?preview_version=4",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer test" },
      }),
    );
  });

  it("downloads stage and cumulative artifacts with their version identity", async () => {
    const stageBlob = new Blob(["stage"], { type: "text/html" });
    const cumulativeBlob = new Blob(["cumulative"], { type: "text/html" });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        blob: vi.fn().mockResolvedValue(stageBlob),
      })
      .mockResolvedValueOnce({
        ok: true,
        blob: vi.fn().mockResolvedValue(cumulativeBlob),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      wplusSopApi.downloadStageReportArtifact("sop-1", {
        stageId: "stage-1",
        revision: 2,
        reportNo: 7,
        artifactId: "stage_sop_html",
      }),
    ).resolves.toBe(stageBlob);
    await expect(
      wplusSopApi.downloadCumulativeArtifact("sop-1", {
        previewVersion: 5,
        artifactId: "cumulative_html",
      }),
    ).resolves.toBe(cumulativeBlob);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/wplus-sop/sessions/sop-1/stage-report-artifacts/stage_sop_html?stage_id=stage-1&revision=2&report_no=7&download=true",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/wplus-sop/sessions/sop-1/cumulative-artifacts/cumulative_html?preview_version=5&download=true",
      expect.any(Object),
    );
  });

  it("reports an unexpected SSE EOF so the workspace can reconnect", async () => {
    const read = vi.fn().mockResolvedValue({ done: true, value: undefined });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read }) },
    });
    vi.stubGlobal("fetch", fetchMock);
    const onError = vi.fn();

    const subscription = wplusSopApi.subscribeSessionEvents(
      "sop/1",
      7,
      vi.fn(),
      onError,
    );
    await subscription.done;

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/wplus-sop/sessions/sop%2F1/events?after_state_version=7",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Accept: "text/event-stream",
          Authorization: "Bearer test",
        }),
      }),
    );
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "W+ SOP 事件流已结束" }),
    );
  });
});
