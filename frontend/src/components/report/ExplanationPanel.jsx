import { DiagnosticsList } from '../../pages/PageParts.jsx';
import { isUsableExplanation } from '../../pages/reportData.js';
import { entries, riskLabel } from './presentation.js';
import ExplanationText from './ExplanationText.jsx';

export default function ExplanationPanel({ evidence, explanationRecord, mode }) {
  const explanation = explanationRecord?.explanation;
  const available = evidence?.status === 'available' && typeof evidence.source_snippet === 'string';
  return (
    <aside className="oi-explanation-panel" aria-label="当前证据的中文辅助解释">
      <h2>中文辅助解释</h2>
      {available && isUsableExplanation(explanation)
        ? <><p className="oi-explanation-summary">{explanation.summary}</p><ExplanationText text={explanation.why_affected} /><h3>建议检查</h3><ExplanationText text={explanation.suggested_check} ordered />
          <dl className="oi-explanation-meta"><div><dt>业务风险</dt><dd>{riskLabel(explanation.risk_level)}</dd></div><div><dt>解释置信度</dt><dd>{explanation.confidence}</dd></div></dl>
          <p className="oi-explanation-note">置信度描述解释结果，不代表代码运行失败的概率。</p>
        </>
        : <div className="oi-report-unavailable" role="status"><b>解释暂不可用</b><p>当前没有可对应的解释，请阅读源码、静态判断原因及诊断。</p></div>}
      {!!entries(explanationRecord?.diagnostics).length && <div className="oi-explanation-diagnostics"><DiagnosticsList diagnostics={explanationRecord.diagnostics} /></div>}
      <details className="oi-explanation-details"><summary>解释来源说明</summary><p className="oi-explanation-note">{mode === 'demo' ? '当前演示样例采用规则解释。' : '当前报告未提供解释生成方式标识，解释可能来自规则或配置的模型。'} 请求成功和解释非空均不能证明 DeepSeek 真实调用成功。</p></details>
    </aside>
  );
}
