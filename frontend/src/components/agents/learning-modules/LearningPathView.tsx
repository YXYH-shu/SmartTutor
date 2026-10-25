import { useState } from 'react';
import { ArrowRight, Check, ChevronDown, Clock3, Flag, ListChecks, Route, Target } from 'lucide-react';
import type { PlanData, PlanStage } from './moduleData';

function StageDetail({ stage, number }: { stage: PlanStage; number: number }) {
  return <section className="lm-stage-detail" aria-label={`第${number}阶段详情`}>
    <div className="lm-stage-detail-heading"><span className="lm-stage-number">{stage.id || `P${number}`}</span><div><p className="lm-eyebrow">阶段 {number} · 学习安排</p><h3>{stage.name}</h3></div>{stage.duration && <span className="lm-duration"><Clock3 size={14} />{stage.duration}</span>}</div>
    <div className="lm-stage-detail-grid">
      <div><h4><Target size={16} />学习目标</h4><p>{stage.objective || '本次结果未提供该阶段的学习目标。'}</p>{stage.reason && <><h4><Route size={16} />推荐理由</h4><p>{stage.reason}</p></>}</div>
      <div><h4><ListChecks size={16} />检查点</h4>{stage.checkpoints.length > 0 ? <ul className="lm-checkpoints">{stage.checkpoints.map((text, i) => <li key={i}><Check size={14} />{text}</li>)}</ul> : <p>本次结果未提供检查点。</p>}{stage.outcome && <p className="lm-outcome"><Flag size={14} />{stage.outcome}</p>}</div>
    </div>
  </section>;
}

export function LearningPathView({ data }: { data: PlanData }) {
  const [selected, setSelected] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const index = Math.min(selected, Math.max(0, data.stages.length - 1));
  return <div className="lm-result">
    <section className="lm-target" aria-label="规划目标"><span className="lm-detail-icon"><Target size={23} /></span><div><p className="lm-eyebrow">本次学习目标{data.targetId ? ` · 题目 ${data.targetId}` : ''}</p><h3>{data.target || '本次结果未提供目标题目'}</h3></div><div className="lm-target-meta"><span>{data.stages.length} 个阶段</span>{data.estimatedTime && <span><Clock3 size={14} />{data.estimatedTime}</span>}</div></section>
    <section aria-labelledby="lm-path-heading">
      <div className="lm-section-heading"><div><p className="lm-eyebrow">LEARNING JOURNEY</p><h3 id="lm-path-heading">一步一步，构建知识路径</h3></div><span className="lm-muted">按规划顺序学习</span></div>
      <p className="lm-description">选择一个阶段，查看学习目标与检查点。下方展示的是规划安排。</p>
      <ol className="lm-path-grid" aria-label="学习路径阶段">
        {data.stages.map((stage, i) => <li key={`${stage.id}-${i}`}><button type="button" className="lm-stage-card" aria-pressed={i === index} onClick={() => { setSelected(i); setExpanded(false); }}><span className="lm-stage-card-top"><span className="lm-stage-number">{stage.id || `P${i + 1}`}</span><span className="lm-planned">已规划</span></span><h4>{stage.name}</h4><p>{stage.objective || '点击查看阶段详情'}</p><span className="lm-stage-card-footer">{stage.duration || `阶段 ${i + 1}`}<ArrowRight size={16} aria-hidden="true" /></span></button></li>)}
      </ol>
      <div className="lm-path-toolbar"><span className="lm-muted">{expanded ? `正在查看全部 ${data.stages.length} 个阶段` : `当前查看：${data.stages[index]?.id || `P${index + 1}`}`}</span><button type="button" className="lm-text-button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? '收起全部' : '展开全部阶段'}<ChevronDown size={16} style={{ transform: expanded ? 'rotate(180deg)' : undefined }} /></button></div>
      <div className="lm-stage-details" aria-live="polite">{expanded ? data.stages.map((stage, i) => <StageDetail key={`${stage.id}-${i}`} stage={stage} number={i + 1} />) : data.stages[index] && <StageDetail stage={data.stages[index]} number={index + 1} />}</div>
    </section>
    {data.rationale && <section className="lm-insight"><h3><Route size={18} />规划说明</h3><p>{data.rationale}</p></section>}
  </div>;
}
