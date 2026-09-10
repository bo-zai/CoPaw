import { describe, expect, it, vi } from "vitest";
import { loadSessionMessages } from "./ChatAnywhereSessionsContext";

type LoadSessionMessagesOptions = Parameters<typeof loadSessionMessages>[0];

function createHttpError(status: number, message: string) {
  return Object.assign(new Error(message), { status });
}

function createOptions(
  getSession: ReturnType<typeof vi.fn>,
): LoadSessionMessagesOptions["options"] {
  return {
    api: {
      getSession,
    },
  } as unknown as LoadSessionMessagesOptions["options"];
}

describe("loadSessionMessages session detail errors", () => {
  it("finishes loading when the active session is cleared while a stale request drains", async () => {
    let resolveRequest: (session: { messages: unknown[] }) => void = () => {};
    const request = new Promise<{ messages: unknown[] }>((resolve) => {
      resolveRequest = resolve;
    });
    const getSession = vi.fn().mockReturnValue(request);
    const setMessages = vi.fn();
    const setSessionLoading = vi.fn();
    let currentSessionId: string | undefined = "17846028251220000";

    const staleLoad = loadSessionMessages({
      requestedSessionId: currentSessionId,
      clearBeforeLoad: true,
      options: createOptions(getSession),
      setMessages,
      getCurrentSessionId: () => currentSessionId,
      setSessionLoading,
      setSessionNotFound: vi.fn(),
    });

    currentSessionId = undefined;
    const clearedLoad = await loadSessionMessages({
      requestedSessionId: currentSessionId,
      clearBeforeLoad: true,
      finishLoadingWithoutSession: true,
      options: createOptions(getSession),
      setMessages,
      getCurrentSessionId: () => currentSessionId,
      setSessionLoading,
      setSessionNotFound: vi.fn(),
    });

    expect(clearedLoad).toBe(false);
    expect(setSessionLoading).toHaveBeenLastCalledWith(false);

    resolveRequest({ messages: [] });
    await expect(staleLoad).resolves.toBe(false);
    expect(setSessionLoading).toHaveBeenCalledTimes(2);
    expect(setSessionLoading).toHaveBeenNthCalledWith(1, true);
    expect(setSessionLoading).toHaveBeenNthCalledWith(2, false);
  });

  it("preserves normal loading state when no session is active", async () => {
    const setMessages = vi.fn();
    const setSessionLoading = vi.fn();

    const applied = await loadSessionMessages({
      requestedSessionId: undefined,
      clearBeforeLoad: true,
      options: createOptions(vi.fn()),
      setMessages,
      getCurrentSessionId: () => undefined,
      setSessionLoading,
      setSessionNotFound: vi.fn(),
    });

    expect(applied).toBe(false);
    expect(setMessages).toHaveBeenCalledWith([]);
    expect(setSessionLoading).not.toHaveBeenCalled();
  });

  it("records an active HTTP 404 and finishes loading", async () => {
    const error = createHttpError(404, "missing");
    const setSessionNotFound = vi.fn();
    const setSessionLoading = vi.fn();
    const setMessages = vi.fn();

    const applied = await loadSessionMessages({
      requestedSessionId: "chat-missing",
      clearBeforeLoad: true,
      options: createOptions(vi.fn().mockRejectedValue(error)),
      setMessages,
      getCurrentSessionId: () => "chat-missing",
      setSessionLoading,
      setSessionNotFound,
    });

    expect(applied).toBe(false);
    expect(setSessionNotFound).toHaveBeenCalledOnce();
    expect(setSessionNotFound).toHaveBeenCalledWith(true);
    expect(setSessionLoading).toHaveBeenNthCalledWith(1, true);
    expect(setSessionLoading).toHaveBeenNthCalledWith(2, false);
    expect(setMessages).toHaveBeenCalledWith([]);
  });

  it("does not mark a successful session as missing", async () => {
    const setMessages = vi.fn();
    const setSessionNotFound = vi.fn();

    const applied = await loadSessionMessages({
      requestedSessionId: "chat-valid",
      clearBeforeLoad: false,
      options: createOptions(
        vi.fn().mockResolvedValue({
          id: "chat-valid",
          name: "Valid chat",
          messages: [{ id: "message-1" }],
        }),
      ),
      setMessages,
      getCurrentSessionId: () => "chat-valid",
      setSessionNotFound,
    });

    expect(applied).toBe(true);
    expect(setSessionNotFound).not.toHaveBeenCalled();
    expect(setMessages).toHaveBeenCalledWith([
      { id: "message-1", history: true },
    ]);
  });

  it("can refresh generating state without scheduling a reconnect", async () => {
    const emitSpy = vi.spyOn(
      await import("./useChatAnywhereEventEmitter"),
      "emit",
    );
    await loadSessionMessages({
      requestedSessionId: "chat-generating",
      clearBeforeLoad: false,
      reconnectIfGenerating: false,
      options: createOptions(
        vi.fn().mockResolvedValue({ messages: [], generating: true }),
      ),
      setMessages: vi.fn(),
      getCurrentSessionId: () => "chat-generating",
    });
    expect(emitSpy).not.toHaveBeenCalled();
    emitSpy.mockRestore();
  });

  it("ignores a stale HTTP 404 after the active session changes", async () => {
    let rejectRequest: (error: Error) => void = () => {};
    const request = new Promise((_, reject) => {
      rejectRequest = reject;
    });
    let currentSessionId = "chat-old";
    const setSessionNotFound = vi.fn();
    const setSessionLoading = vi.fn();

    const loadPromise = loadSessionMessages({
      requestedSessionId: "chat-old",
      clearBeforeLoad: false,
      options: createOptions(vi.fn().mockReturnValue(request)),
      setMessages: vi.fn(),
      getCurrentSessionId: () => currentSessionId,
      setSessionLoading,
      setSessionNotFound,
    });

    currentSessionId = "chat-current";
    rejectRequest(createHttpError(404, "old chat missing"));

    await expect(loadPromise).resolves.toBe(false);
    expect(setSessionNotFound).not.toHaveBeenCalled();
    expect(setSessionLoading).toHaveBeenCalledTimes(1);
    expect(setSessionLoading).toHaveBeenCalledWith(true);
  });

  it("preserves the existing rejection path for non-404 failures", async () => {
    const error = createHttpError(500, "server error");

    await expect(
      loadSessionMessages({
        requestedSessionId: "chat-error",
        clearBeforeLoad: false,
        options: createOptions(vi.fn().mockRejectedValue(error)),
        setMessages: vi.fn(),
        getCurrentSessionId: () => "chat-error",
        setSessionNotFound: vi.fn(),
      }),
    ).rejects.toBe(error);
  });
});
