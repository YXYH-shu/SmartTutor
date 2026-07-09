/**
 * KgService
 *
 * 用户级知识图谱(KG)接口。后端 task 7 提供端点:
 *   GET /api/v1/users/knowledge-graph
 *
 * 返回 schema:
 *   { nodes: Array<{ id, label, mastery?, status? }>; edges: Array<{ source, target }> }
 *
 * mastery<0.4 视为本轮重点候选(isHighlight),可被 Path Bar / Hero 强提示。
 */

import api from './api';
import type { KnowledgeNode } from '@/types';

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
}

export interface KnowledgeGraphData {
  nodes: KnowledgeNode[];
  edges: KnowledgeGraphEdge[];
}

class KgService {
  /** 拉取当前用户的 KG(所有掌握的知识点 + 关系边) */
  async getUserKnowledgeGraph(): Promise<KnowledgeGraphData> {
    const res = await api.get('/api/v1/users/knowledge-graph');
    const raw = res.data ?? { nodes: [], edges: [] };
    return {
      nodes: (raw.nodes ?? []).map((n: any) => {
        const mastery =
          typeof n.mastery === 'number'
            ? n.mastery
            : typeof n.mastery === 'string' && n.mastery !== ''
              ? Number(n.mastery)
              : undefined;
        return {
          id: String(n.id),
          label: String(n.label ?? n.id),
          mastery: typeof mastery === 'number' && !Number.isNaN(mastery) ? mastery : undefined,
          status: n.status as KnowledgeNode['status'] | undefined,
          // mastery<0.4 视为本轮重点候选
          isHighlight: typeof mastery === 'number' && mastery < 0.4,
        };
      }),
      edges: (raw.edges ?? []).map((e: any) => ({
        source: String(e.source),
        target: String(e.target),
      })),
    };
  }
}

export const kgService = new KgService();
export default kgService;
