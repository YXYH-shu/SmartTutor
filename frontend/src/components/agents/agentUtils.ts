/**
 * Agent 面板共享 helpers。
 * 抽出独立文件避免 AgentStudio / AgentDetailDrawer 之间循环依赖。
 */

import {
  Heart,
  Shield,
  Brain,
  Route,
  Library,
  Users,
  BookOpen,
  Sparkles,
  HandHeart,
  type LucideIcon,
} from 'lucide-react';

export const ICON_MAP: Record<string, LucideIcon> = {
  Heart,
  Shield,
  Brain,
  Route,
  Library,
  Users,
  BookOpen,
  Sparkles,
  HandHeart,
};

export function getIcon(name: string): LucideIcon {
  return ICON_MAP[name] ?? Sparkles;
}

/** 按点路径取值;a.b.c 安全取 obj.a.b.c,任一层 null/undefined 返回 undefined */
export function getValueByPath(obj: Record<string, unknown> | null, path: string): unknown {
  if (!obj) return undefined;
  return path.split('.').reduce<unknown>((acc, key) => {
    if (acc == null) return acc;
    return (acc as Record<string, unknown>)[key];
  }, obj);
}

/** 解析 agentTrace[name].content 字符串为对象;非对象或解析失败返回 null */
export function parseAgentContent(content: string | undefined): Record<string, unknown> | null {
  if (!content) return null;
  try {
    const parsed = JSON.parse(content);
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
