import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, ArrowRight, Brain, CheckCircle2, Clock3, Info, LoaderCircle, Route, X } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { DiagnosisView } from './DiagnosisView';
import { LearningPathView } from './LearningPathView';
import { normalizeDiagnosis, normalizePlan, resolveModuleSnapshot, type ModuleName, type ModuleState } from './moduleData';
import './learningModules.css';

const stateLabels: Record<ModuleState, string> = { pending: '尚未执行', running: '正在处理', completed: '已完成', error: '执行失败', timeout: '执行超时', incomplete: '结果不完整', interrupted: '执行已中断' };
const diagnosisSteps = [
  ['读取学习记录', '以学生已有作答和学习记录作为诊断依据。'],
  ['KT 评估', '估计知识点掌握程度，呈现模型返回的数值。'],
  ['薄弱点筛选', '从评估结果中识别需要优先巩固的知识点。'],
  ['诊断解读', '整理诊断摘要，形成后续学习建议。'],
];
const planningSteps = [
  ['接收诊断', '承接本轮已有的学情分析结果。'],
  ['确定目标', '根据返回的目标题目明确本次规划方向。'],
  ['规划计算', '生成有先后顺序的知识点学习路线。'],
  ['整理结果', '展示各阶段的目标、理由与检查点。'],
];
function durationLabel(ms: number | undefined) {
  if (ms === undefined || !Number.isFinite(ms)) return '耗时暂无记录';
  const seconds = Math.max(0, ms / 1000);
  return seconds < 60 ? `${seconds.toFixed(1)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`;
}

export function LearningModuleDialog({ name, onClose }: { name: ModuleName; onClose: () => void }) {
  const trace = useChatStore((s) => s.agentTrace);
  const turn = useChatStore((s) => s.currentTurn);
  const currentAgent = useChatStore((s) => s.currentAgent);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const isLoading = useChatStore((s) => s.isLoading);
  const selectAgent = useChatStore((s) => s.setSelectedDetailAgent);
  const [section, setSection] = useState<'result' | 'process'>('result');
  const [, refreshClock] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const headingId = useId();
  const descriptionId = useId();
  const busy = isStreaming || isLoading;
  const snapshot = resolveModuleSnapshot(name, trace[name], turn, currentAgent, busy);
  const diagnosis = normalizeDiagnosis(name === 'cognitive_diagnosis' ? snapshot.output : resolveModuleSnapshot('cognitive_diagnosis', trace.cognitive_diagnosis, turn, currentAgent, busy).output);
  const plan = normalizePlan(snapshot.output);
  const isDiagnosis = name === 'cognitive_diagnosis';
  const otherName: ModuleName = isDiagnosis ? 'learning_path' : 'cognitive_diagnosis';
  const other = resolveModuleSnapshot(otherName, trace[otherName], turn, currentAgent, busy);
  const sameTurnDiagnosis = resolveModuleSnapshot('cognitive_diagnosis', trace.cognitive_diagnosis, turn, currentAgent, busy);
  const canSwitch = !snapshot.historical && !other.historical && !!other.output && ['completed', 'incomplete'].includes(other.state);
  const canUseDiagnosis = !snapshot.historical && !sameTurnDiagnosis.historical && sameTurnDiagnosis.state === 'completed' && diagnosis.points.length > 0;
  const weakPoints = diagnosis.points.filter((point) => point.status === 'weak');
  const hasResults = isDiagnosis ? diagnosis.points.length > 0 : plan.stages.length > 0;
  const showResults = hasResults && ['completed', 'incomplete'].includes(snapshot.state);
  const Icon = isDiagnosis ? Brain : Route;

  useEffect(() => { setSection('result'); }, [name]);
  useEffect(() => {
    if (snapshot.state !== 'running') return;
    const timer = window.setInterval(() => refreshClock((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [snapshot.state]);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const app = document.getElementById('root');
    const previousInert = app?.inert ?? false;
    if (app) app.inert = true;
    document.body.style.overflow = 'hidden';
    const dialog = dialogRef.current;
    dialog?.focus();
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input, select, textarea, [tabindex="0"], summary') ?? []).filter((element) => element.getClientRects().length > 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeRef.current(); }
      if (event.key !== 'Tab') return;
      const elements = focusable();
      const first = elements[0], last = elements[elements.length - 1];
      if (!first || !last) { event.preventDefault(); dialog?.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { event.preventDefault(); first.focus(); }
    };
    const onFocus = (event: FocusEvent) => { if (event.target instanceof Node && dialog && !dialog.contains(event.target)) dialog.focus(); };
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('focusin', onFocus);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('focusin', onFocus);
      document.body.style.overflow = previousOverflow;
      if (app) app.inert = previousInert;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(
    <div className={`lm-overlay ${isDiagnosis ? 'lm-diagnosis' : 'lm-planning'}`} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="lm-dialog" role="dialog" aria-modal="true" aria-labelledby={headingId} aria-describedby={descriptionId} ref={dialogRef} tabIndex={-1}>
        <header className="lm-header">
          <div className="lm-header-main"><span className="lm-module-icon"><Icon size={29} strokeWidth={1.5} /></span><div><p className="lm-eyebrow">学习洞察 · {isDiagnosis ? '了解学情' : '规划下一步'}</p><h2 id={headingId}>{isDiagnosis ? '认知诊断' : '路径规划'}</h2><p className="lm-subtitle" id={descriptionId}>{isDiagnosis ? '从知识状态看见学习起点' : '让每一步学习都有清晰方向'}</p></div></div>
          <div className="lm-header-actions"><span className={`lm-state lm-state-${snapshot.state}`} role="status">{snapshot.state === 'running' ? <LoaderCircle size={14} className="lm-spin" /> : snapshot.state === 'completed' ? <CheckCircle2 size={14} /> : <span className="lm-status-dot" />}{stateLabels[snapshot.state]}</span><button type="button" className="lm-icon-button" onClick={onClose} aria-label="关闭模块详情"><X size={21} /></button></div>
          <div className="lm-header-meta"><span>{(isDiagnosis ? diagnosis.studentId : plan.studentId) ? `学生 ${isDiagnosis ? diagnosis.studentId : plan.studentId}` : '学生编号未提供'}</span><span className={snapshot.historical ? 'lm-historical' : ''}>{snapshot.historical ? '历史结果 · 非本轮计算' : '本轮结果'}</span><span><Clock3 size={13} />{durationLabel(snapshot.durationMs)}</span></div>
        </header>
        <nav className="lm-nav" aria-label="模块详情内容"><div><button type="button" aria-pressed={section === 'result'} onClick={() => setSection('result')}>结果概览</button><button type="button" aria-pressed={section === 'process'} onClick={() => setSection('process')}>处理流程</button></div>{canSwitch && <button type="button" className="lm-switch" onClick={() => selectAgent(otherName)}>{isDiagnosis ? '查看学习路径' : '查看认知诊断'}<ArrowRight size={15} /></button>}</nav>
        <div className="lm-body">
          {snapshot.historical && <div className="lm-notice"><Info size={17} /><p>当前展示历史结果。本轮尚未返回此模块的新结果。</p></div>}
          {['error', 'timeout', 'interrupted', 'incomplete'].includes(snapshot.state) && <div className="lm-notice lm-notice-warning" role="alert"><Info size={18} /><div><strong>{stateLabels[snapshot.state]}</strong><p>{snapshot.state === 'timeout' ? '本次节点执行超时，未生成可用结果。可以回到对话重新发起。' : snapshot.state === 'incomplete' ? '本次返回的数据不完整，以下仅展示已提供的内容。' : snapshot.state === 'interrupted' ? '本次处理已停止，尚未获得完整结果。可以回到对话重新发起。' : '本次处理未能生成可用结果。可以回到对话重新发起。'}</p></div></div>}
          {section === 'result' ? <>
            {showResults ? <>
              {!isDiagnosis && <div className="lm-input-summary"><Brain size={18} /><div><span className="lm-eyebrow">承接学情诊断</span><p>{canUseDiagnosis ? `${diagnosis.points.length} 个知识点已评估，${diagnosis.weakCount} 个待巩固。${diagnosis.topic}` : '当前没有可关联的同轮诊断结果。以下展示本次规划返回的路线。'}</p>{canUseDiagnosis && weakPoints.length > 0 && <details className="lm-weak-input"><summary>待巩固：{weakPoints.slice(0, 3).map((point) => point.name).join('、')}{weakPoints.length > 3 ? `等 ${weakPoints.length} 项` : ''}</summary><div className="lm-weak-tags">{weakPoints.map((point, i) => <span key={i}>{point.name}</span>)}</div></details>}</div></div>}
              {isDiagnosis ? <DiagnosisView key={turn?.turnId ?? 'history'} data={diagnosis} /> : <LearningPathView key={turn?.turnId ?? 'history'} data={plan} />}
            </> : <div className="lm-empty"><span className="lm-empty-icon"><Icon size={34} strokeWidth={1.3} /></span><h3>{snapshot.state === 'running' ? (isDiagnosis ? '正在分析学习状态' : '正在生成学习路径') : snapshot.state === 'pending' ? (isDiagnosis ? '等待认知诊断' : '等待路径规划') : '暂无可展示的结果'}</h3><p>{snapshot.state === 'running' ? '结果返回后会自动呈现在这里，可切换「处理流程」了解各环节。' : snapshot.state === 'pending' ? '回到对话发起相应请求，节点执行后会在这里展示真实结果。' : '请根据上方状态说明回到对话重新尝试。'}</p>{snapshot.state === 'running' && <div className="lm-skeleton" aria-hidden="true">{[0, 1, 2].map((i) => <span key={i} />)}</div>}</div>}
          </> : <section className="lm-process"><p className="lm-eyebrow">PROCESS OVERVIEW</p><h3>{isDiagnosis ? '从学习记录到诊断解读' : '从学情输入到五阶段路线'}</h3><p className="lm-description">以下为处理环节说明。当前系统提供节点整体状态，尚未提供各环节的独立实时进度。</p><ol>{(isDiagnosis ? diagnosisSteps : planningSteps).map(([title, description], i) => <li key={title}><span className="lm-process-number">{String(i + 1).padStart(2, '0')}</span><div><h4>{title}</h4><p>{description}</p></div></li>)}</ol><div className="lm-process-result"><Icon size={21} /><div><h4>节点整体状态：{stateLabels[snapshot.state]}</h4><p>{snapshot.historical ? '历史结果' : '本轮执行'} · {durationLabel(snapshot.durationMs)}{showResults ? ` · 已返回 ${isDiagnosis ? `${diagnosis.points.length} 个知识点评估` : `${plan.stages.length} 个规划阶段`}` : ''}</p></div></div></section>}
        </div>
        <footer className="lm-footer"><button type="button" className="lm-text-button" onClick={onClose}><ArrowLeft size={15} />返回对话</button><span>{isDiagnosis ? '知识状态来自本次诊断输出' : '阶段内容来自结构化规划结果'} · {snapshot.state === 'running' ? '结果返回后自动更新' : '点击卡片查看详情'}</span></footer>
      </div>
    </div>, document.body,
  );
}
