/**
 * 课题 4.4 可视化：情感分析 / 共情回应 视图模型。
 *
 * 适配层把后端 trace 的原始 JSON 归一化成这里的结构，组件只消费视图模型：
 * 后端字段缺失、类型不符时适配层统一兜底，组件不会崩。
 * 共用元件复用 trace43 的 primitives / motion。
 */

export type Json = Record<string, unknown>;

/** 情感模型 v2 三分类 */
export type EmotionPolarity = 'positive' | 'negative' | 'neutral' | '';

export interface EmotionView {
  polarity: EmotionPolarity;
  polarityLabel: string;
  /** 模型给出的判定依据 */
  reason: string;
  hasData: boolean;
}

export interface EmpathyView {
  /** 生成的共情回应文本 */
  response: string;
  /** 使用的心理技巧 */
  techniques: string[];
  /** 本轮采用的教师人格 */
  persona: string;
  hasData: boolean;
}
