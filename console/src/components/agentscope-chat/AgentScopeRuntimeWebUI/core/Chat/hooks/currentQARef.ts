import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";
import type { ChatRequestOwner } from "./requestOwnership";

export type LiveResponseMessage = IAgentScopeRuntimeWebUIMessage & {
  liveHeaderTimestamp?: number;
};

export type CurrentQARef = React.MutableRefObject<{
  request?: IAgentScopeRuntimeWebUIMessage;
  response?: LiveResponseMessage;
  abortController?: AbortController;
  activeRequestOwner?: ChatRequestOwner;
  stopPending?: boolean;
}>;
