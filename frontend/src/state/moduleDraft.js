// Module intent is independent of function signatures. Validate owns legality.
export const MODULE_CHANGE_TYPES = Object.freeze([
  { value: 'rename_module', label: '重命名模块', description: '拟定新的根模块名称，检查保留的旧导入。' },
  { value: 'remove_module', label: '删除模块', description: '分析模块消失后的导入断裂；不会删除文件。' },
])

export function createModuleDraft(type = 'rename_module') {
  if (!MODULE_CHANGE_TYPES.some(item => item.value === type)) throw new RangeError('不支持的模块变更类型。')
  return { changeType: type, operation: type === 'rename_module' ? { newModuleName: '' } : { confirmed: false } }
}

export function updateModuleDraft(change, patch) {
  const draft = createModuleDraft(change.changeType)
  const field = change.changeType === 'rename_module' ? 'newModuleName' : 'confirmed'
  draft.operation[field] = patch?.[field] ?? change.operation[field]
  return draft
}

export function buildModulePayload(target, change) {
  return {
    change_domain: 'module', change_type: change.changeType, target_module_id: target,
    ...(change.changeType === 'rename_module' ? { new_module_name: change.operation.newModuleName.trim() } : {}),
  }
}

export function matchesModuleIntent(spec, payload) {
  return spec?.change_domain === 'module' && spec.change_type === payload.change_type
    && spec.target_module_id === payload.target_module_id && spec.operation?.change_type === payload.change_type
    && spec.modifies_source === false && spec.analysis_scope === 'project_root_static'
    && (payload.change_type === 'rename_module'
      ? spec.operation.new_module_name === payload.new_module_name && spec.after?.module_id === payload.new_module_name
        && spec.after.file === `${payload.new_module_name}.py`
      : spec.after === null)
}

export function moduleIdentity(module) {
  return module && typeof module.module_id === 'string' && typeof module.file === 'string'
    && /^[0-9a-f]{64}$/.test(module.source_hash)
    ? JSON.stringify([module.module_id, module.file, module.source_hash]) : null
}
