import { useEffect, useRef } from 'react';
import DomainSelector from './DomainSelector.jsx';
import { WorkflowNotes } from './WorkflowParts.jsx';
import { ErrorNotice } from '../../pages/PageParts.jsx';

const headings = {
  function: ['选择分析函数', '用完整函数标识确认目标，再核对它的文件与原始签名。'],
  module: ['选择分析模块', '确认真实相对路径与可支持范围，再拟定模块变化。'],
  symbol: ['选择模块符号', '先确认模块，再选择本次源码中的公开变量或常量。'],
};

export default function SelectionLayout({ domain = 'function', mode, error, onReset, onSelectDomain, contentOnly, children }) {
  const previousDomain = useRef(domain);
  const switching = previousDomain.current !== domain;
  useEffect(() => { previousDomain.current = domain; }, [domain]);
  if (contentOnly) return <>{children}</>;
  const [title, description] = headings[domain];
  return <div className="oi-workflow-page oi-functions-page">
    <section className="page-heading"><div><h1>{title}</h1><p>{description}</p></div><button className="ghost-action" type="button" onClick={onReset}>重新开始</button></section>
    <DomainSelector domain={domain} mode={mode} onSelect={onSelectDomain} />
    <WorkflowNotes current={2} mode={mode} /><ErrorNotice error={error} />
    {/* Replace one content tree immediately; no outgoing copy or deferred state. */}
    <div className={`oi-domain-content${switching ? ' is-switching' : ''}`} key={domain} data-domain={domain}>{children}</div>
  </div>;
}
