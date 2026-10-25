import { useState } from 'react';
import { ArrowUpRight, Focus, Layers3, Sparkles } from 'lucide-react';
import type { DiagnosisData, KnowledgePoint } from './moduleData';

const labels: Record<KnowledgePoint['status'], string> = {
  mastered: '掌握较好', developing: '有待提升', weak: '待巩固', unknown: '暂无评估',
};
const percent = (value: number | null) => value === null ? '—' : `${(value * 100).toFixed(1)}%`;

export function DiagnosisView({ data }: { data: DiagnosisData }) {
  const [selected, setSelected] = useState(0);
  const selectedIndex = Math.min(selected, Math.max(0, data.points.length - 1));
  const point = data.points[selectedIndex];
  return (
    <div className="lm-result">
      <div className="lm-metrics">
        <div className="lm-metric"><span><Layers3 size={16} />诊断知识点</span><strong>{data.points.length}<small>个</small></strong></div>
        <div className="lm-metric"><span><Focus size={16} />待巩固知识点</span><strong>{data.weakCount}<small>个</small></strong></div>
        <div className="lm-metric"><span><Sparkles size={16} />诊断来源</span><strong className="lm-source">{data.source || '未提供'}</strong></div>
      </div>
      <section aria-labelledby="lm-map-heading">
        <div className="lm-section-heading">
          <div><p className="lm-eyebrow">KNOWLEDGE MAP</p><h3 id="lm-map-heading">知识掌握图谱</h3></div>
          <div className="lm-legend" aria-label="掌握度图例">
            <span className="lm-mastered">≥70% 掌握较好</span><span className="lm-developing">40–70% 有待提升</span><span className="lm-weak">＜40% 待巩固</span>
          </div>
        </div>
        {data.topic && <p className="lm-description">{data.topic}</p>}
        {data.points.some(item => item.relevanceRank) && <p className="lm-description">按与当前主题的相关度排列；拓展补充项关联较弱，供额外学情参考。</p>}
        <div className="lm-knowledge-grid" role="group" aria-label="知识点掌握度">
          {data.points.map((item, index) => (
            <button type="button" key={`${item.id}-${index}`} className={`lm-knowledge lm-${item.status}`} aria-pressed={selectedIndex === index} onClick={() => setSelected(index)}>
              {item.relevanceRank && <span className="lm-eyebrow">#{item.relevanceRank} · {item.relevanceTier === 'extended' ? '拓展补充' : '主题相关'}</span>}
              <span className="lm-knowledge-name">{item.name}</span>
              <strong>{percent(item.mastery)}</strong>
              <span className="lm-knowledge-bottom"><span>{labels[item.status]}</span><ArrowUpRight size={14} aria-hidden="true" /></span>
              <span className="lm-mastery-track" aria-hidden="true"><span style={{ width: `${(item.mastery ?? 0) * 100}%` }} /></span>
            </button>
          ))}
        </div>
        {point && <div className="lm-point-detail" aria-live="polite">
          <span className="lm-detail-icon"><Focus size={21} /></span>
          <div><p className="lm-eyebrow">当前查看</p><h4>{point.name} <span className={`lm-point-value lm-${point.status}`}>{percent(point.mastery)} · {labels[point.status]}</span></h4><p>{point.evidence || '该知识点暂无额外诊断说明。'}</p>{point.relevanceReason && <p>关联说明：{point.relevanceReason}</p>}</div>
        </div>}
      </section>
      {(data.summary || data.actions.length > 0) && <section className="lm-insight" aria-label="诊断解读">
        <h3><Sparkles size={18} />诊断解读</h3>
        {data.summary && <p>{data.summary}</p>}
        {data.actions.length > 0 && <ul>{data.actions.map((action, i) => <li key={i}>{action}</li>)}</ul>}
      </section>}
    </div>
  );
}
