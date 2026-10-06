// Presentation only. These groups do not resolve targets, assign impacts, or
// change coverage. In particular, a missing project target is not proof that
// the call belongs to a standard library or is unrelated to the change.
const groups = [
  { id: 'coverage', title: '源码与分析范围',
    description: '先检查源码读取、语法错误和不支持的分析范围。文件解析成功也不代表调用关系全部确认。' },
  { id: 'binding', title: '绑定歧义与名称遮蔽',
    description: '名称可能来自参数、局部变量、重复赋值或不确定的导入。请核对赋值和传参位置，不能按同名直接认定调用目标。' },
  { id: 'dynamic', title: '对象属性与动态调用',
    description: '目标涉及对象属性、复杂表达式或动态行为。请检查对象类型与实际调用方式；当前不生成猜测性的调用关系。' },
  { id: 'external', title: '已识别的项目外或内置目标',
    description: '这些记录已提供项目外或内置目标的依据。库内部行为仍不属于本次项目源码分析范围。' },
  { id: 'target', title: '目标未确认（可能含项目外依赖）',
    description: '可能包含标准库、第三方依赖、内置函数或未收录的项目内目标。现有记录不足以区分，不能直接认定与本次变更无关。' },
  { id: 'other', title: '其他诊断',
    description: '保留原始诊断和位置；未识别的原因不会被自动归类为无影响。' },
];

const coverageReasons = new Set([
  'module_parse_failed', 'module_source_unavailable', 'syntax_error', 'SyntaxError', 'read_error', 'encoding_error',
  'unsupported_call_scope', 'unsupported_module_layout', 'unsupported_importer', 'unsupported_target_module',
  'unsupported_module', 'unsupported_symbol', 'unsupported_reference_scope', 'relative_import_unsupported',
  'relative_import_without_package', 'relative_import_beyond_package', 'namespace_package_unsupported',
  'package_import_unsupported', 'special_module_unsupported', 'module_level_call', 'caller_not_indexed',
]);
const bindingReasons = new Set([
  'local_name_shadows_target', 'local_binding', 'module_name_rebound', 'callee_module_name_rebound',
  'import_binding_rebound', 'symbol_rebound', 'ambiguous_module', 'ambiguous_project_module',
  'standard_library_name_collision', 'read_before_import', 'read_before_definition', 'call_before_binding',
  'conditional_or_local_import_unsupported', 'wildcard_import_unsupported', 'imported_member_not_proven',
  'package_member_not_proven', 'package_path_rebound', 'package_context_rebound',
]);
const dynamicReasons = new Set([
  'unsupported_callee_expression', 'attribute_chain_unsupported', 'module_binding_missing',
  'attribute_root_not_module', 'object_attribute_not_proven', 'object_module_binding_not_proven',
  'class_namespace_unresolved', 'dynamic_import', 'dynamic_symbol_write', 'dynamic_definition_unsupported',
  'dynamic_exports_unsupported', 'dynamic_or_complex_reference_in_source', 'project_dynamic_write_unsupported',
  'attribute_write_unsupported', 'project_attribute_write_unsupported',
]);
const targetReasons = new Set([
  'module_not_in_project', 'symbol_not_in_project', 'import_binding_unresolved', 'name_not_indexed',
  'attribute_target_not_indexed', 'unknown_target', 'module_used_as_function',
]);

export function diagnosticEntries(diagnostics) {
  const categories = Array.isArray(diagnostics) ? [['diagnostic', diagnostics]] : Object.entries(diagnostics || {});
  return categories.flatMap(([category, values]) => Array.isArray(values) ? values.map(entry => ({
    category, detail: entry !== null && typeof entry === 'object' ? entry : { message: String(entry) },
  })) : []);
}

function groupId({ category, detail }) {
  const reason = detail.reason || detail.code || detail.kind;
  if (coverageReasons.has(reason) || ['parse_errors', 'parse_diagnostics', 'syntax_diagnostics', 'import_syntax_diagnostics', 'unsupported_scopes'].includes(category)) return 'coverage';
  if (bindingReasons.has(reason)) return 'binding';
  if (dynamicReasons.has(reason)) return 'dynamic';
  if (reason === 'builtin') return 'external';
  if (targetReasons.has(reason) || ['unresolved_calls', 'unresolved_imports', 'unresolved_references'].includes(category)) return 'target';
  return 'other';
}

export function groupDiagnostics(entries) {
  const buckets = new Map(groups.map(group => [group.id, []]));
  entries.forEach(entry => buckets.get(groupId(entry)).push(entry));
  return groups.map(group => ({ ...group, entries: buckets.get(group.id) })).filter(group => group.entries.length);
}
