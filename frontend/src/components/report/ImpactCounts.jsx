import { useEffect, useId, useRef, useState } from 'react';

const groups = [
  { title: '确定影响', className: 'is-confirmed', metrics: [
    { title: '直接影响', key: 'direct_impact_count', unit: '调用点', help: '这些调用原本符合函数参数要求，修改后不再符合。可查看源码证据，确认缺少的必填参数。' },
  ] },
  { title: '影响传播', metrics: [
    { title: '1 层间接影响', key: 'indirect_1hop_count', unit: '上游函数', help: '这些函数调用了存在直接影响的函数，建议进一步检查。这表示一层上游调用关系，不代表一定会运行失败。' },
    { title: '2 层间接影响', key: 'indirect_2hop_count', unit: '上游函数', help: '这些函数通过另一层调用关联到直接影响，建议进一步检查。这表示两层上游调用关系，不代表一定会运行失败。' },
  ] },
  { title: '分析边界', className: 'is-boundary', metrics: [
    { title: '人工检查', key: 'manual_review_count', unit: '记录', help: '现有代码信息不足以判断这些调用是否受本次变更影响，请结合代码和实际传入的参数人工检查。' },
    { title: '未解析调用', key: 'unresolved_call_count', unit: '记录', help: '尚未确认这些调用与项目内函数的关系，无法据此判断影响或画出传播路径。数量不代表出错次数。' },
  ] },
];

// Presentation state only: one help message at a time, independent of report
// selection. Counts retain the original summary keys, units and missing value.
export default function ImpactCounts({ summary }) {
  const id = useId();
  const root = useRef(null);
  const [active, setActive] = useState(null);

  useEffect(() => {
    if (!active) return;
    const owner = root.current.ownerDocument;
    function dismissOutside(event) {
      if (!event.target.closest?.('.oi-stat-help') || !root.current.contains(event.target)) setActive(null);
    }
    function dismissEscape(event) {
      if (event.key === 'Escape') setActive(null);
    }
    owner.addEventListener('pointerdown', dismissOutside);
    owner.addEventListener('keydown', dismissEscape);
    return () => {
      owner.removeEventListener('pointerdown', dismissOutside);
      owner.removeEventListener('keydown', dismissEscape);
    };
  }, [active]);

  return <section className="oi-report-counts" aria-label="影响统计" ref={root}>
    {groups.map((group, groupIndex) => <section className={`oi-stat-group ${group.className || ''}`} key={group.title} aria-labelledby={`${id}-group-${groupIndex}`}
      onPointerLeave={(event) => {
        // Keep hover help readable while moving from the icon into its message.
        const keyboardFocused = !!event.currentTarget.querySelector('button:focus-visible');
        setActive((current) => group.metrics.some((metric) => metric.key === current?.key) && !current.pinned && !keyboardFocused ? null : current);
      }}>
      <h2 id={`${id}-group-${groupIndex}`}>{group.title}</h2>
      <dl>
        {group.metrics.map((metric) => {
          const visible = active?.key === metric.key;
          const tooltipId = `${id}-${metric.key}-help`;
          return <div className="oi-stat-metric" key={metric.key}>
            <dt><span>{metric.title}</span><span className="oi-stat-help"
              onPointerEnter={(event) => { if (event.pointerType === 'mouse') setActive((current) => current?.key === metric.key ? current : { key: metric.key, pinned: false }); }}>
              <button type="button" className="oi-stat-help-button" aria-label={`了解${metric.title}`} aria-describedby={tooltipId} aria-expanded={visible} aria-controls={tooltipId}
                onFocus={(event) => { if (event.currentTarget.matches(':focus-visible')) setActive({ key: metric.key, pinned: false }); }}
                onBlur={(event) => { if (!event.currentTarget.parentElement.contains(event.relatedTarget)) setActive((current) => current?.key === metric.key ? null : current); }}
                onClick={() => setActive((current) => current?.key === metric.key && current.pinned ? null : { key: metric.key, pinned: true })}>
                <span aria-hidden="true">?</span>
              </button>
              <span id={tooltipId} className="oi-stat-tooltip" role="tooltip" hidden={!visible}>{metric.help}</span>
            </span></dt>
            <dd><strong>{summary?.[metric.key] ?? '—'}</strong><span>{metric.unit}</span></dd>
          </div>;
        })}
      </dl>
    </section>)}
  </section>;
}
