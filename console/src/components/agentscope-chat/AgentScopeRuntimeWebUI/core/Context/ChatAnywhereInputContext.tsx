import { createContext, useContextSelector } from "use-context-selector";
import { IAgentScopeRuntimeWebUIInputContext } from "@/components/agentscope-chat";
import { useGetState } from "ahooks";
import { useCallback, useEffect, useRef } from "react";
import { ChatAnywhereSessionsContext } from "./ChatAnywhereSessionsContext";

export const ChatAnywhereInputContext =
  createContext<IAgentScopeRuntimeWebUIInputContext>({
    loading: false,
    stopping: false,
    setStopping: () => {},
    setLoading: () => {},
    getLoading: () => false,
    disabled: false,
    setDisabled: () => {},
    getDisabled: () => false,
  });

export function ChatAnywhereInputContextProvider(props: {
  children: React.ReactNode | React.ReactNode[];
}) {
  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.currentSessionId,
  );
  const getCurrentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.getCurrentSessionId,
  );

  const [loading, _setLoading, getLoading] = useGetState<boolean | string>(
    false,
  );
  const [disabled, _setDisabled, getDisabled] = useGetState<boolean | string>(
    false,
  );
  const [stopping, _setStopping] = useGetState(false);

  const stateMapRef = useRef<
    Record<
      string,
      {
        loading: boolean | string;
        disabled: boolean | string;
        stopping: boolean;
      }
    >
  >({});
  const prevSessionIdRef = useRef<string | undefined>(undefined);

  const setLoading = useCallback(
    (value: boolean | string) => {
      const sessionId = getCurrentSessionId();
      if (sessionId) {
        if (!stateMapRef.current[sessionId]) {
          stateMapRef.current[sessionId] = {
            loading: false,
            disabled: false,
            stopping: false,
          };
        }
        stateMapRef.current[sessionId].loading = value;
      }
      _setLoading(value);
    },
    [getCurrentSessionId, _setLoading],
  );

  const setDisabled = useCallback(
    (value: boolean | string) => {
      const sessionId = getCurrentSessionId();
      if (sessionId) {
        if (!stateMapRef.current[sessionId]) {
          stateMapRef.current[sessionId] = {
            loading: false,
            disabled: false,
            stopping: false,
          };
        }
        stateMapRef.current[sessionId].disabled = value;
      }
      _setDisabled(value);
    },
    [getCurrentSessionId, _setDisabled],
  );

  const setStopping = useCallback(
    (value: boolean, sessionId?: string) => {
      const targetSessionId = sessionId ?? getCurrentSessionId();
      if (targetSessionId) {
        if (!stateMapRef.current[targetSessionId]) {
          stateMapRef.current[targetSessionId] = {
            loading: false,
            disabled: false,
            stopping: false,
          };
        }
        stateMapRef.current[targetSessionId].stopping = value;
        if (targetSessionId === getCurrentSessionId()) {
          _setLoading(
            value || Boolean(stateMapRef.current[targetSessionId].loading),
          );
          _setStopping(value);
        }
      } else {
        _setStopping(value);
      }
    },
    [getCurrentSessionId, _setLoading, _setStopping],
  );

  useEffect(() => {
    if (
      prevSessionIdRef.current &&
      prevSessionIdRef.current !== currentSessionId
    ) {
      if (stateMapRef.current[prevSessionIdRef.current]) {
        stateMapRef.current[prevSessionIdRef.current].loading = false;
        stateMapRef.current[prevSessionIdRef.current].disabled = false;
      }
    }

    const state = currentSessionId
      ? stateMapRef.current[currentSessionId]
      : undefined;
    _setLoading(Boolean(state?.stopping) || state?.loading || false);
    _setStopping(Boolean(state?.stopping));
    _setDisabled(state?.disabled ?? false);

    prevSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  return (
    <ChatAnywhereInputContext.Provider
      value={{
        loading,
        stopping,
        setStopping,
        setLoading,
        getLoading,
        disabled,
        setDisabled,
        getDisabled,
      }}
    >
      {props.children}
    </ChatAnywhereInputContext.Provider>
  );
}

export const useChatAnywhereInput = (
  selector: (
    v: Partial<IAgentScopeRuntimeWebUIInputContext>,
  ) => Partial<IAgentScopeRuntimeWebUIInputContext>,
) => {
  return useContextSelector(ChatAnywhereInputContext, selector);
};
