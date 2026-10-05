export const SYMBOL_CHANGE_TYPES = [
  { value: 'rename_module_symbol', label: '重命名模块符号', description: '公开变量 / 常量 · 追踪旧名称引用' },
  { value: 'remove_module_symbol', label: '删除模块符号', description: '分析拟定定义删除 · 不修改源码' },
]
export function createSymbolDraft(type = 'rename_module_symbol') {
  const changeType = SYMBOL_CHANGE_TYPES.some(t => t.value === type) ? type : 'rename_module_symbol'
  return { changeType, operation: changeType === 'rename_module_symbol' ? { newSymbolName: '' } : { confirmed: false } }
}
export function updateSymbolDraft(draft, fields) {
  const key = draft.changeType === 'rename_module_symbol' ? 'newSymbolName' : 'confirmed'
  return { ...draft, operation: { ...draft.operation, ...(Object.hasOwn(fields, key) ? { [key]: key === 'confirmed' ? fields[key] === true : String(fields[key]) } : {}) } }
}
export function buildSymbolPayload(id, draft) {
  return { change_domain: 'symbol', change_type: draft.changeType, target_symbol_id: id,
    ...(draft.changeType === 'rename_module_symbol' ? { new_symbol_name: draft.operation.newSymbolName.trim() } : {}) }
}
export function symbolIdentity(symbol) {
  return symbol && typeof symbol.source_hash === 'string' && /^[a-f0-9]{64}$/.test(symbol.source_hash)
    ? JSON.stringify([symbol.symbol_id, symbol.module_id, symbol.file, symbol.name, symbol.source_hash,
      symbol.line, symbol.column, symbol.end_line, symbol.end_column, symbol.definition, symbol.value_source, symbol.annotation_source]) : null
}
export function matchesSymbolIntent(spec, change) {
  if (!spec || spec.change_domain !== 'symbol' || spec.analysis_scope !== 'project_root_static_symbols' || spec.modifies_source !== false
    || spec.target_symbol_id !== change.target_symbol_id || spec.change_type !== change.change_type
    || spec.operation?.change_type !== change.change_type || spec.target_module_id !== spec.before?.module_id) return false
  if (change.change_type === 'remove_module_symbol') return spec.after === null
  const before = spec.before, after = spec.after
  return spec.operation.new_symbol_name === change.new_symbol_name && after?.name === change.new_symbol_name
    && after.symbol_id === `${before.module_id}.${change.new_symbol_name}` && after.module_id === before.module_id
    && after.file === before.file && after.source_hash === before.source_hash
    && after.value_source === before.value_source && after.annotation_source === before.annotation_source
    && ['line','column','end_line','end_column','kind','selectable','reason'].every(key => after[key] === before[key])
}
