import { entries, impactLabel, locationText } from './presentation.js';

function TracePath({ path, number, direct }) {
  const symbols = entries(path.symbols);
  const sites = entries(path.call_sites);
  if (symbols.length < 2 || symbols.some((symbol) => typeof symbol !== 'string' || !symbol)
    || sites.length !== symbols.length - 1) {
    return <p className="oi-report-unavailable">路径暂不可用：当前路径资料不完整。</p>;
  }
  return (
    <div className="oi-trace-path">
      <p className="oi-path-origin">{direct ? '直接影响对应的单个确定调用' : `后端已提供路径 ${number}`}</p>
      <ol className="oi-trace-chain" aria-label={symbols.join(' → ')} style={{ '--oi-trace-count': symbols.length }}>
        {symbols.map((symbol, index) => {
          const target = index === symbols.length - 1;
          const directCaller = index === symbols.length - 2;
          return <li key={index} style={{ '--oi-trace-order': Math.min(symbols.length - 1 - index, 3) }} className={`oi-trace-step${target ? ' is-target' : ''}${directCaller ? ' is-direct-caller' : ''}`}>
            <div className="oi-trace-node">
              <span className="oi-trace-point" aria-hidden="true" />
              <span className="oi-trace-role">{target ? '变更目标' : directCaller ? '直接受影响的调用方' : '上游，建议检查'}</span>
              <code>{symbol}</code>
            </div>
            {!target && <span className="oi-trace-site">{`调用点 ${index + 1}：${locationText(sites[index])}`}</span>}
          </li>;
        })}
      </ol>
      <details className="oi-trace-reference"><summary>原始直接影响证据引用：</summary><code>{path.direct_evidence_reference || '未提供'}</code></details>
    </div>
  );
}

export default function TraceView({ finding, evidence }) {
  const direct = finding?.impact_type === 'direct';
  // A Direct finding already records one confirmed edge. It has no Indirect
  // propagation_path; show that exact edge without inventing upstream nodes.
  const paths = direct && finding.caller_symbol_id && finding.target_symbol_id ? [{
    symbols: [finding.caller_symbol_id, finding.target_symbol_id],
    call_sites: [finding],
    direct_evidence_reference: evidence?.evidence_reference,
  }] : entries(evidence?.propagation_path);
  return (
    <section className="oi-trace-view" aria-label="当前影响的调用路径">
      <header><h2>调用追踪</h2><span className={direct ? 'oi-impact-type is-direct' : 'oi-impact-type'}>{impactLabel(finding?.impact_type)}</span></header>
      <p className="oi-trace-scope">{direct ? '该调用因本次变更从兼容变为不兼容。' : '位于确定直接影响的上游，建议检查；静态路径不保证运行时失败。'} 范围仅限当前影响记录。</p>
      {!paths.length
        ? <div className="oi-report-unavailable" role="status"><b>路径暂不可用</b><p>当前记录没有可对应的传播路径，不能推测调用关系。</p></div>
        : paths.map((path, index) => <TracePath key={index} path={path} number={index + 1} direct={direct} />)}
      {!direct && paths.length > 0 && <p className="oi-trace-scope">源码对应后端选定的代表调用位置。其他路径节点仅展示已有名称和调用点，范围不覆盖完整项目调用图。</p>}
    </section>
  );
}
