import { useRef } from 'react';
import MovingMarker from '../../motion/MovingMarker.jsx';
import { findingLocation, impactLabel, locationText } from './presentation.js';

const groups = [
  ['direct', '直接影响', '调用点'],
  ['indirect_1hop', '1 层间接影响', '上游函数'],
  ['indirect_2hop', '2 层间接影响', '上游函数'],
  ['other', '其他记录', '记录'],
];

export default function ImpactIndex({ findings, activeIndex, onSelect, reviewCounts, onReview }) {
  const groupsRef = useRef(null);
  // Carry the original index through visual grouping; never renumber Evidence slots.
  const indexed = findings.map((finding, index) => ({ finding, index }));
  return (
    <aside className="oi-impact-index" aria-label="影响索引">
      <header><h2>影响索引</h2><p>选择记录，核查对应证据。</p></header>
      <label className="oi-impact-picker">
        <span>选择影响记录</span>
        <select value={findings.length ? activeIndex : ''} disabled={!findings.length}
          onChange={(event) => onSelect(Number(event.target.value))}>
          {!findings.length && <option value="">没有确定影响</option>}
          {indexed.map(({ finding, index }) => <option key={index} value={index}>
            {impactLabel(finding.impact_type)} · {finding.caller_symbol_id || finding.impacted_symbol_id || '未提供'} · {locationText(findingLocation(finding))}
          </option>)}
        </select>
      </label>
      <div className="oi-impact-groups" ref={groupsRef}>
        {groups.map(([type, title, unit]) => {
          const rows = indexed.filter(({ finding }) => type === 'other'
            ? !groups.slice(0, 3).some(([known]) => finding.impact_type === known)
            : finding.impact_type === type);
          if (!rows.length) return null;
          return <section className="oi-impact-group" key={type}>
            <h3>{title}<span>{rows.length} {unit}</span></h3>
            {rows.map(({ finding, index }) => <button type="button"
              className={`oi-impact-row ${type === 'direct' ? 'is-direct' : type === 'other' ? '' : 'is-indirect'}${index === activeIndex ? ' is-selected' : ''}`}
              data-finding-index={index} key={index} aria-pressed={index === activeIndex}
              onClick={() => onSelect(index)}>
              <b>{finding.caller_symbol_id || finding.impacted_symbol_id || '未提供'}</b>
              <span>{`位置：${locationText(findingLocation(finding))}`}</span>
              <small>{type === 'direct' ? '兼容 → 不兼容' : type === 'other' ? '请检查原始记录' : '上游，建议检查'}</small>
            </button>)}
          </section>;
        })}
        {!findings.length && <p className="oi-index-empty">当前没有确定影响记录。</p>}
        <MovingMarker containerRef={groupsRef} selector=".is-selected" identity={activeIndex} className={findings[activeIndex]?.impact_type === 'direct' ? 'is-direct' : ''} />
      </div>
      {Object.values(reviewCounts).some(Boolean) && <div className="oi-index-reviews">
        <p>独立检查记录</p>
        {[['manual', '人工检查'], ['unresolved', '未解析调用'], ['preexisting', '修改前已有问题']].map(([key, label]) =>
          <button type="button" key={key} disabled={!reviewCounts[key]} onClick={() => onReview(key)}>
            <span>{label}</span><span>{reviewCounts[key]}</span>
          </button>)}
        <small>这些记录不占用确定影响的证据槽位。</small>
      </div>}
    </aside>
  );
}
