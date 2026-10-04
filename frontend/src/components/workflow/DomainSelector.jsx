export default function DomainSelector({ domain = 'function', mode, onSelect }) {
  return <fieldset className="oi-change-type-selector oi-domain-selector"><legend>分析领域</legend>
    <div className="oi-change-type-options">
      {[['function', '函数签名变更', '四种参数变化 · 比较调用前后兼容性'], ['module', '模块变更', '根目录 Python 模块 · 追踪静态导入依赖']].map(([value, label, detail]) =>
        <label className={`oi-change-type-option${domain === value ? ' is-selected' : ''}`} key={value}>
          <input type="radio" name="change-domain" aria-label={label} checked={domain === value} disabled={mode === 'demo' && value === 'module'} onChange={() => onSelect?.(value)} />
          <span><b>{label}</b><small>{mode === 'demo' && value === 'module' ? '模块变更请使用实际项目' : detail}</small></span>
        </label>)}
    </div>
  </fieldset>
}
