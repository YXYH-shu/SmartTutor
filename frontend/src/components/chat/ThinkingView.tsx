/**
 * ThinkingView 已升级为 AgentInteractionLog,见同目录 AgentInteractionLog.tsx。
 *
 * 此文件保留 re-export 以避免破坏现有引用(ChatContainer.tsx / MessageBubble.tsx
 * 等都从 './ThinkingView' import)。功能完全等价,折叠交互保留。
 *
 * 后续 task 8 完成迁移后可删除此文件。
 */

export { AgentInteractionLog as ThinkingView, AgentInteractionLog as default } from './AgentInteractionLog';
