import { createGlobalStyle } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

export default createGlobalStyle`
.welcome-center-layout {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  min-width: 0;
  min-height: 0;
  padding: 40px 20px;
  gap: 0;
  background: url('/chat-bg.png') center/cover no-repeat;
  background: linear-gradient(180deg, #E8EEFF 0%, #F1F2F7 40%, #F5F5FA 100%);
}

.welcome-greeting {
  font-size: 22px;
  font-weight: 600;
  color: ${DESIGN_TOKENS.colorTextDark};
  line-height: 33px;
  margin-bottom: 40px;
  text-align: center;
}

.welcome-input-card {
  position: relative;
  box-sizing: border-box;
  width: ${DESIGN_TOKENS.inputCardWidth + 40}px;
  max-width: 100%;
  min-width: 0;
  background-color: ${DESIGN_TOKENS.colorBgCard};
  border-radius: ${DESIGN_TOKENS.radiusCard}px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
  box-shadow: 0px 0px 8px 0px rgba(0, 0, 0, 0.08);
}

.welcome-input-placeholder {
  font-size: 14px;
  line-height: 22px;
  color: ${DESIGN_TOKENS.colorTextMuted};
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  width: 100%;
  min-height: 24px;
  max-height: 200px;
  font-family: inherit;
  padding: 4px 0;
  overflow: auto;
}

.welcome-skill-editor {
  min-height: 24px;
  white-space: pre-wrap;

  &:empty::before {
    color: ${DESIGN_TOKENS.colorTextMuted};
    content: attr(data-placeholder);
    pointer-events: none;
  }
}

.welcome-input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-left: -6px;
}

.welcome-input-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.welcome-input-send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: ${DESIGN_TOKENS.colorPrimary};
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s ease;

  &:hover {
    opacity: 0.85;
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.welcome-tabs-area {
  width: ${DESIGN_TOKENS.inputCardWidth}px;
  max-width: 100%;
  margin-bottom: 28px;
}

.welcome-cases-area {
  width: 935px;
  margin: 0 auto;
}

.scenario-preset-selector {
  --segment-track-bg: #EDF1F7;
  --segment-track-border: #E2E7F0;
  --segment-text: #4F5D73;
  --segment-hover-bg: #F7F9FD;
  --segment-active-bg: #FFFFFF;
  --segment-active-text: #2957DC;
  --segment-active-border: #D5E0FF;
  --chip-bg: #FFFFFF;
  --chip-text: #526075;
  --chip-border: #DDE3EC;
  --chip-hover-bg: #F4F7FE;
  --chip-hover-text: #2957DC;
  --chip-hover-border: #C7D6FF;
  --chip-active-bg: #EEF4FF;
  --chip-active-text: #2957DC;
  --chip-active-border: #C7D6FF;
  --chip-active-hover-bg: #E4ECFF;
  --chip-pressed-bg: #DBE6FF;
  box-sizing: border-box;
  width: ${DESIGN_TOKENS.inputCardWidth + 40}px;
  max-width: 100%;
  min-width: 0;
  margin-bottom: 0;
}

.scenario-preset-selector-shell {
  box-sizing: border-box;
  width: ${DESIGN_TOKENS.inputCardWidth + 40}px;
  max-width: 100%;
  min-width: 0;
}

.scenario-preset-domain-selector,
.scenario-preset-capability-row,
.welcome-scene-list {
  display: flex;
  gap: 8px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.scenario-preset-domain-selector {
  justify-content: center;
  padding: 2px 0 12px;
}

.scenario-preset-domain-track {
  align-items: center;
  background: var(--segment-track-bg);
  border: 1px solid var(--segment-track-border);
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  display: inline-flex;
  gap: 2px;
  max-width: 100%;
  overflow-x: auto;
  padding: 3px;
  scrollbar-width: thin;
}

.scenario-preset-domain-selector.is-single .scenario-preset-domain-track {
  background: transparent;
  border-color: transparent;
  padding: 0;
}

.scenario-preset-domain-card {
  align-items: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  color: var(--segment-text);
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  gap: 6px;
  justify-content: center;
  height: 32px;
  min-height: 32px;
  padding: 0 12px;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;

  &:hover:not(:disabled) {
    background: var(--segment-hover-bg);
    color: var(--segment-active-text);
  }

  &:focus-visible {
    outline: 2px solid ${DESIGN_TOKENS.colorPrimary};
    outline-offset: 2px;
  }

  &.is-active {
    background: var(--segment-active-bg);
    border-color: var(--segment-active-border);
    color: var(--segment-active-text);
  }

  &.is-active:hover:not(:disabled) {
    background: var(--segment-active-bg);
    border-color: #C7D6FF;
    color: var(--segment-active-text);
  }

  &:active:not(:disabled):not(.is-active) {
    background: var(--chip-pressed-bg);
    color: var(--segment-active-text);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: .55;
  }
}

.scenario-preset-capability-row {
  margin: 0 -20px;
  padding: 4px 20px 12px;
}

.scenario-preset-capability-tab,
.welcome-scene-button {
  background: var(--chip-bg);
  border: 1px solid var(--chip-border);
  border-radius: 999px;
  border-bottom-left-radius: 999px;
  border-bottom-right-radius: 999px;
  border-top-left-radius: 999px;
  border-top-right-radius: 999px;
  color: var(--chip-text);
  cursor: pointer;
  flex: 0 0 auto;
  font: inherit;
  font-size: 13px;
  height: 30px;
  line-height: 18px;
  padding: 0 12px;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;

  &:hover:not(:disabled) {
    background: var(--chip-hover-bg);
    border-color: var(--chip-hover-border);
    color: var(--chip-hover-text);
  }

  &:focus-visible {
    outline: 2px solid ${DESIGN_TOKENS.colorPrimary};
    outline-offset: 2px;
  }

  &.is-active {
    background: var(--chip-active-bg);
    border-color: var(--chip-active-border);
    color: var(--chip-active-text);
    font-weight: 500;
  }

  &.is-active:hover:not(:disabled) {
    background: var(--chip-active-hover-bg);
    border-color: var(--chip-active-border);
    color: var(--chip-active-text);
  }

  &:active:not(:disabled) {
    background: var(--chip-pressed-bg);
    border-color: var(--chip-hover-border);
    color: var(--chip-active-text);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: .55;
  }
}

.welcome-scene-button {
  background: #E9EDF4;
  border-color: transparent;
  font-size: 12px;
  height: 26px;
  padding: 0 10px;

  &:hover:not(:disabled) {
    background: #F1F3F6;
    border-color: transparent;
    color: var(--chip-text);
  }
}

.welcome-scene-strip {
  align-items: center;
  background: #F7F9FC;
  border-bottom: 1px solid #E5E7EB;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  display: flex;
  gap: 10px;
  margin: -16px -20px 0;
  min-height: 44px;
  overflow: hidden;
  padding: 6px 16px;
}

.welcome-scene-title {
  color: ${DESIGN_TOKENS.colorTextDark};
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 600;
}

.welcome-scene-list {
  width: 100%;
}

.welcome-scenario-marker {
  color: ${DESIGN_TOKENS.colorPrimary};
  font-size: 14px;
  font-weight: 500;
}
`;
