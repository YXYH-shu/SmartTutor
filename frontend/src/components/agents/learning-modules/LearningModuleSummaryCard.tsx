import { ArrowUpRight, Brain, Route } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { normalizeDiagnosis, normalizePlan, resolveModuleSnapshot, type ModuleName } from './moduleData';
import './learningSummary.css';

/** Compact entry cards: longer findings belong in the module detail dialog. */
export function LearningModuleSummaryCard({ name }: { name: ModuleName }) {
  const trace = useChatStore((s) => s.agentTrace[name]);
  const turn = useChatStore((s) => s.currentTurn);
  const currentAgent = useChatStore((s) => s.currentAgent);
  const busy = useChatStore((s) => s.isLoading || s.isStreaming);
  const selectAgent = useChatStore((s) => s.setSelectedDetailAgent);
  const snapshot = resolveModuleSnapshot(name, trace, turn, currentAgent, busy);
  const diagnosis = normalizeDiagnosis(snapshot.output);
  const plan = normalizePlan(snapshot.output);
  const isDiagnosis = name === 'cognitive_diagnosis';
  const title = isDiagnosis ? '认知诊断' : '路径规划';
  const Icon = isDiagnosis ? Brain : Route;
  const hasResult = !!snapshot.output && ['completed', 'incomplete'].includes(snapshot.state);
  const status = snapshot.historical ? '历史结果' : ({
    pending: '等待执行', running: '处理中', completed: '本轮重点',
    incomplete: '结果不完整', timeout: '执行超时', error: '执行失败', interrupted: '已中断',
  }[snapshot.state]);
  const studentId = isDiagnosis ? diagnosis.studentId : plan.studentId;
  const source = isDiagnosis ? diagnosis.source : '';

  return (
    <button type="button" className="learning-summary-card" onClick={() => selectAgent(name)} aria-label={`${title}，${status}，查看详情`}>
      <div className="learning-summary-heading">
        <span className="learning-summary-icon"><Icon size={19} /></span>
        <h3>{title}</h3>
        <span className="learning-summary-badge">{status}</span>
      </div>
      <dl className="learning-summary-metrics">
        <div><dt>{isDiagnosis ? '知识点' : '规划阶段'}</dt><dd>{hasResult ? `${isDiagnosis ? diagnosis.points.length : plan.stages.length} ${isDiagnosis ? '个' : '阶段'}` : '—'}</dd></div>
        <div><dt>{isDiagnosis ? '待巩固' : '预计学习时长'}</dt><dd title={!isDiagnosis && hasResult ? plan.estimatedTime : undefined}>{hasResult ? (isDiagnosis ? `${diagnosis.weakCount} 个` : plan.estimatedTime || '未提供') : '—'}</dd></div>
      </dl>
      <div className="learning-summary-footer">
        <span title={[source, studentId && `学生 ${studentId}`].filter(Boolean).join(' · ')}>{[source, studentId && `学生 ${studentId}`].filter(Boolean).join(' · ') || '等待节点结果'}</span>
        <span>查看详情 <ArrowUpRight size={13} /></span>
      </div>
    </button>
  );
}
