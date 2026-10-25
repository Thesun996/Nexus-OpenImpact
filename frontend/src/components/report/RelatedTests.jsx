import { SourceLink } from '../workspace/SourceWorkspace.jsx';

export default function RelatedTests({ report }) {
  const related = report.related_tests;
  const candidates = related?.status === 'available' && Array.isArray(related.candidates) ? related.candidates : [];
  return <section className="oi-related-tests" aria-label="相关测试与检查理由">
    <header><h2>相关测试与检查理由</h2><span>{candidates.length} 个候选</span></header>
    <p>依据真实调用路径定位候选测试。未实际收集或运行测试，关联不保证测试会执行到受影响位置或运行失败。</p>
    {candidates.length > 0 && <p>上方辅助解释未使用这份测试列表；本区补充具体候选位置，实际覆盖与执行结果仍需确认。</p>}
    {report.coverage?.status === 'partial' && <p className="oi-provider-note">未列出的测试仍可能需要检查。</p>}
    {!candidates.length && <p role="status">{related?.status === 'unavailable'
      ? '相关测试定位暂不可用，请结合源码与已有影响结果人工选择测试。'
      : related ? '当前支持的路径内未定位到相关测试。空列表不代表无需回归测试。'
        : '当前报告未提供测试定位信息。请确认 ZIP 包含测试文件；模块和符号领域暂未提供测试定位。'}</p>}
    <ol className="oi-test-candidates">{candidates.map(candidate => <li key={candidate.test_symbol_id}>
      <h3><code>{candidate.test_symbol_id}</code><span>{candidate.relationship === 'direct' ? '包含直接影响调用' : '上游测试，建议检查'}</span></h3>
      <p>测试定义：<code>{candidate.file}:{candidate.line}</code></p>
      <p>{candidate.reason}</p>
      <details><summary>候选运行定位</summary><code>{candidate.node_id}</code><p>请在自己的项目环境中核对测试配置和依赖。这里未验证 pytest 是否会收集该函数。</p></details>
      {candidate.paths.map(path => <details className="oi-test-path" key={path.direct_evidence_reference} open>
        <summary>关联调用路径</summary>
        <p className="oi-test-chain"><code>{[path.call_sites[0]?.caller_symbol_id, ...path.call_sites.map(site => site.callee_symbol_id)].join(' → ')}</code></p>
        <ol>{path.call_sites.map((site, index) => <li key={`${site.file}:${site.line}:${site.column}`}>
          <p><b>{index === path.call_sites.length - 1 ? '原始直接影响位置' : '上游调用位置'}</b> <code>{site.file}:{site.line}:{site.column}</code> <SourceLink location={site} sourceHash={site.source_hash} /></p>
          {site.status === 'available' && typeof site.source_snippet === 'string'
            ? <pre tabIndex={0} aria-label="测试关联源码，可横向滚动"><code>{site.source_snippet}</code></pre>
            : <p className="state-message warning">该位置源码证据不可用，请重新分析或人工核查。</p>}
        </li>)}</ol>
        <details><summary>原始证据引用</summary><code>{path.direct_evidence_reference}</code></details>
      </details>)}
    </li>)}</ol>
    {related?.limitations?.length > 0 && <details className="oi-test-limits"><summary>测试定位范围与局限</summary><ul>{related.limitations.map(text => <li key={text}>{text}</li>)}</ul></details>}
  </section>;
}
