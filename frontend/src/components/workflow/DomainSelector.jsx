export default function DomainSelector({ domain = 'function', mode, onSelect }) {
  return <fieldset className="oi-change-type-selector oi-domain-selector"><legend>分析领域</legend>
    <div className="oi-change-type-options">
      {[['function', '函数签名变更', '四种参数变化 · 比较调用前后兼容性'], ['module', '模块变更', '根目录 Python 模块 · 追踪静态导入依赖'], ['symbol', '模块符号变更', '公开变量与常量 · 追踪定义引用']].map(([value, label, detail]) =>
        <label className={`oi-change-type-option${domain === value ? ' is-selected' : ''}`} key={value}>
          <input type="radio" name="change-domain" aria-label={label} checked={domain === value} disabled={mode === 'demo' && value !== 'function'} onChange={() => onSelect?.(value)} />
          <span><b>{label}</b><small>{mode === 'demo' && value !== 'function' ? '此领域请使用实际项目' : detail}</small></span>
        </label>)}
    </div>
  </fieldset>
}
