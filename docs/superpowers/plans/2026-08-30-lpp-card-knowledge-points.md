# LPP Card Knowledge-Point Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LPP debug card display the five backend-recommended knowledge points instead of an empty legacy question sequence.

**Architecture:** `agentConfigs.ts` is frontend-only metadata consumed by the debug-card renderer. Replace its obsolete `recommended_questions` schema and field formatter with the backend's `recommended_knowledge_points` contract. Update the static card metadata so it represents the KT/LPP global LLM configuration rather than a stale GLM-5 override.

**Tech Stack:** React, TypeScript, Vite.

## Global Constraints

- Do not modify LPP Runtime, KT Runtime, routing, or backend response fields.
- The card must render at most five entries as `P{order} · {knowledge_point_name}`.
- Preserve graceful fallback to `-` when the backend returns no knowledge points.
- Do not commit or push unless the user explicitly requests it.

---

### Task 1: Align LPP card metadata with the backend knowledge-point contract

**Files:**
- Modify: `frontend/src/data/agentConfigs.ts:176-213,488-505`
- Test: `frontend` TypeScript production build

**Interfaces:**
- Consumes: `recommended_knowledge_points: Array<{order: number, knowledge_point_id: number|string, knowledge_point_name: string}>` from `LearningPathAgent.finalize_output`.
- Produces: a `recommended_knowledge_points` card field whose formatter returns `P1 · 名称 → … → P5 · 名称`.

- [ ] **Step 1: Write the failing contract assertion**

Add a temporary TypeScript assertion in the frontend buildable source that invokes the `learning_path` formatter with five `recommended_knowledge_points` values and expects `P1 · 食物链 → P2 · 动物感知环境 → …`; this must fail because no such formatter is configured.

- [ ] **Step 2: Run the frontend production build to verify the assertion fails**

Run: `npm run build` from `frontend/`.

Expected: TypeScript/build failure showing the legacy formatter cannot satisfy the knowledge-point contract.

- [ ] **Step 3: Implement the minimal metadata change**

Replace the `recommended_questions` output-schema and display-field definitions with `recommended_knowledge_points`. Format each object with its runtime `order` and `knowledge_point_name`, falling back to `知识点{knowledge_point_id}` only when no name is provided. Update static model metadata to `{ model: '全局配置（本地 Qwen）', temperature: 0.3, maxTokens: 1024, timeout: 180, maxRetries: 1, thinking: false }`.

- [ ] **Step 4: Run the frontend production build to verify it passes**

Run: `npm run build` from `frontend/`.

Expected: exit code 0; TypeScript and Vite build complete.

- [ ] **Step 5: Inspect the diff**

Run: `git diff --check && git diff -- frontend/src/data/agentConfigs.ts`.

Expected: only LPP card metadata and formatting change; no backend changes.
