// Presentation labels only. Never write these strings back into API data/state.
export function parameterKindLabel(kind) {
  return ({ positional_or_keyword: '普通位置或关键字参数', positional_only: '仅位置参数',
    keyword_only: '仅关键字参数', var_positional: '可变位置参数（*args）',
    var_keyword: '可变关键字参数（**kwargs）' })[kind] || '参数类型未识别';
}

export function statusLabel(status) {
  return ({ available: '可用', unavailable: '不可用', complete: '完整', partial: '不完整',
    compatible: '兼容', incompatible: '不兼容', manual_review: '需要人工检查',
    resolved_project: '已确认项目内目标', unresolved: '未能确认目标', unrelated: '与目标无关',
    ok: '解析成功', error: '解析失败', local: '局部绑定', not_applicable: '不适用',
  })[status] || '状态未识别';
}

export function riskLabel(risk) {
  return ({ unknown: '暂无法判断', low: '较低', medium: '中等', high: '较高' })[risk] || '风险信息未提供';
}

export function ruleLabel(rule) {
  return ({
    required_parameter_added_breaks_call: '新增必填参数使原调用不兼容',
    parameter_removed_breaks_call: '删除参数使原调用不兼容',
    parameter_renamed_breaks_keyword_call: '参数改名使原命名传参不兼容',
    parameter_became_required_breaks_call: '参数改为必填使原调用不兼容',
    resolved_upstream_call_path: '已确认的上游调用路径，建议检查',
    argument_expansion_unknown: '展开参数的内容无法确定，需人工检查',
    module_renamed_breaks_project_import: '模块改名使原导入失去目标',
    module_removed_breaks_project_import: '删除模块使原导入失去目标',
    upstream_module_dependency_review: '上游模块依赖，建议检查',
    resolved_upstream_module_path: '已确认的上游模块依赖，建议检查',
    module_symbol_renamed_breaks_reference: '符号改名使原引用失去目标',
    module_symbol_removed_breaks_reference: '删除符号使原引用失去目标',
    upstream_symbol_dependency_review: '上游符号依赖，建议检查',
  })[rule] || '请查看判断依据及原始规则编号';
}

const REASONS = {
  module_not_in_project: '无法确认项目内目标模块', symbol_not_in_project: '无法确认项目内目标符号',
  unsupported_module_layout: '当前只支持项目根目录的普通模块，包与嵌套模块暂不支持',
  module_parse_failed: '源码解析失败，请查看诊断', module_source_unavailable: '源码文件无法读取',
  ambiguous_module: '模块名存在同名或大小写歧义', ambiguous_project_module: '无法唯一确认项目内模块',
  standard_library_name_collision: '模块名与 Python 标准库冲突，暂不作确定性分析',
  special_module_unsupported: '特殊入口、包初始化或保留名称暂不支持',
  invalid_module_name: '模块名不合法', non_normalized_module_name: '模块名称未规范化，无法安全匹配',
  unsupported_importer: '导入来源超出当前支持范围', unsupported_target_module: '目标模块超出当前支持范围',
  unsupported_module: '模块超出当前支持范围', unsupported_symbol: '符号超出当前支持范围',
  relative_import_unsupported: '相对导入暂不支持，需要人工检查',
  relative_import_without_package: '相对导入缺少可确认的普通包', relative_import_beyond_package: '相对导入超出包层级',
  namespace_package_unsupported: '缺少包初始化文件，暂不能确认相对导入', package_path_rebound: '包搜索路径被修改，无法确认静态目标',
  parent_module_is_not_package: '父级名称指向普通文件，无法作为包解析',
  package_context_rebound: '包上下文被修改，无法确认相对导入', package_member_not_proven: '包内成员可能遮蔽子模块，需要人工检查',
  conditional_or_local_import_unsupported: '条件或局部导入的执行环境未确定，需要人工检查',
  package_import_unsupported: '复杂包导入暂不能可靠解析', wildcard_import_unsupported: '通配导入需要人工检查',
  imported_member_not_proven: '无法确认导入成员，可能涉及重导出或重绑定',
  unique_project_root_module: '已唯一确认项目根目录模块', unique_public_module_symbol: '已唯一确认公开模块符号',
  importer_removed: '导入所在模块拟被移除', unsupported_symbol_import: '此符号导入形式暂不支持',
  unsupported_reference_scope: '引用所在作用域暂不支持', import_binding_rebound: '导入名称发生重绑定',
  read_before_import: '引用位置早于导入语句', read_before_definition: '引用位置早于符号定义',
  object_attribute_not_proven: '无法确认对象属性的项目内目标', object_module_binding_not_proven: '无法确认对象绑定的模块',
  attribute_write_unsupported: '属性写入需要人工检查', project_attribute_write_unsupported: '项目存在属性写入，引用需要人工检查',
  project_dynamic_write_unsupported: '项目存在动态写入，引用需要人工检查',
  dynamic_or_complex_reference_in_source: '源码存在动态或复杂引用，需要人工检查',
  dynamic_import: '动态导入无法静态确认，需要人工检查', dynamic_symbol_write: '动态符号写入需要人工检查',
  private_symbol_unsupported: '当前仅分析公开变量和常量，私有名称暂不可选',
  symbol_rebound: '符号存在重复定义或全局写入，无法证明唯一绑定',
  conditional_definition_unsupported: '定义位于条件或异常处理环境中，需要人工检查',
  complex_definition_unsupported: '当前只支持唯一简单字面量赋值或带值注解赋值',
  dynamic_definition_unsupported: '动态命名空间写入使定义无法确定', dynamic_exports_unsupported: '动态导出暂不支持',
  function_symbol: '目标属于函数签名分析领域', local_binding: '名称绑定到局部作用域',
  builtin: '名称绑定到 Python 内置对象', module_binding: '名称绑定到模块', other_static_binding: '名称属于其他静态绑定',
  unsupported_callee_expression: '调用表达式形式暂不支持', attribute_chain_unsupported: '复杂属性链暂不支持',
  local_name_shadows_target: '局部名称遮蔽了目标', module_name_rebound: '模块名称发生重绑定',
  callee_module_name_rebound: '被调用目标在模块中发生重绑定', import_binding_unresolved: '导入目标未能确认',
  module_used_as_function: '调用位置将模块当作函数使用', name_not_indexed: '调用名称不在已确认的函数索引中',
  module_binding_missing: '缺少可确认的模块绑定', attribute_root_not_module: '属性所属对象未确认是模块',
  attribute_target_not_indexed: '属性目标不在已确认的函数索引中',
  module_level_call: '模块顶层调用未纳入函数调用图', caller_not_indexed: '调用方未纳入函数索引',
  unknown_target: '无法确认调用目标',
  class_namespace_unresolved: '类的继承、元类或动态命名空间使调用目标无法可靠确认，请人工检查',
  call_before_binding: '类定义执行到此处时，目标名称尚未完成导入或定义，无法归因于本次变更',
};

const MESSAGES = {
  'target_symbol_id 必须是非空字符串。': '请提供目标函数或符号的完整标识。',
  'change_type 必须是已支持的变更类型。': '请选择当前支持的变更类型。',
  'change 必须是 JSON 对象。': '变更配置格式不正确，请重新配置。',
  'change 包含不支持的字段。': '变更配置包含不支持的内容。',
  'added_parameter 仅需 name 和 kind。': '新增参数配置应包含参数名与参数类型。',
  'added_parameter.name 必须是非空字符串。': '新增参数名不能为空。',
  'insert_before 必须是现有参数名称。': '插入位置应选择当前函数中已有的参数。',
  'insert_before 未指向现有参数。': '所选插入位置不在当前函数参数中，请重新选择。',
  'operation 类型与参数模型不一致。': '变更类型与当前参数配置不一致，请重新配置。',
  'operation 需要结构化新增参数。': '请完整填写新增参数配置。',
  'operation 包含不支持的字段。': '变更配置包含不支持的内容。',
  'operation 新增参数字段不完整或不受支持。': '新增参数配置不完整或不受支持。',
  'parameter_name 必须是合法的 Python 参数名。': '请填写合法的 Python 参数名。',
  'new_parameter_name 必须是合法的 Python 标识符且不能是关键字。': '新参数名应为合法的 Python 标识符，且不能使用关键字。',
  '当前仅支持重命名 positional_or_keyword 和 keyword_only 参数；函数体引用风险不在本轮调用兼容性分析范围内。': '当前仅支持重命名普通位置或关键字参数、仅关键字参数；函数体引用风险不在当前调用兼容性分析范围内。',
  '删除操作仅接受 change_type 和 parameter_name。': '删除操作应包含变更类型与参数名。',
  '重命名操作仅接受 change_type、parameter_name 和 new_parameter_name。': '重命名操作应包含变更类型、原参数名与新参数名。',
  '必填化操作仅接受 change_type 和 parameter_name。': '改为必填的操作应包含变更类型与参数名。',
  'operation 必须是 JSON 对象。': '变更配置格式不正确，请重新配置。',
  'operation 的变更类型尚未注册。': '当前不支持该变更类型。',
  'operation 类型尚未注册。': '当前不支持该变更类型。',
  '旧声明字段与 operation 不一致。': '原声明与变更配置不一致。',
  'ChangeSpec 缺少 operation 参数。': '变更配置缺少操作内容。',
  '参数注解必须是源码文本或 null。': '参数注解应为源码文本，也可以不提供。',
  '必填化配置仅需 target_symbol_id、change_type 和 parameter_name。': '改为必填的配置应包含目标函数、变更类型与参数名。',
  '删除配置仅需 target_symbol_id、change_type 和 parameter_name。': '删除配置应包含目标函数、变更类型与参数名。',
  '重命名配置仅需 target_symbol_id、change_type、parameter_name 和 new_parameter_name。': '重命名配置应包含目标函数、变更类型、原参数名与新参数名。',
  '该符号位于确定 Direct Impact 的上游调用路径中，建议检查；静态路径不保证运行时失败。': '该函数位于确定直接影响的上游调用路径中，建议检查；静态路径不保证运行时失败。',
};

export function reasonLabel(reason) {
  if (!reason) return '原因未提供';
  if (REASONS[reason] || MESSAGES[reason]) return REASONS[reason] || MESSAGES[reason];
  // Preserve Chinese explanations and their real identifiers verbatim. Unknown
  // internal codes remain available in technical details, never guessed away.
  return /[\u3400-\u9fff]/u.test(reason) ? reason : '暂未提供中文说明，请查看技术详情';
}

export function diagnosticLabel(code) {
  return ({
    invalid_zip: 'ZIP 文件无效', empty_zip: 'ZIP 文件为空', invalid_change_json: '变更配置格式错误',
    invalid_change_config: '变更配置无效', fingerprint_mismatch: '项目版本不一致',
    invalid_analysis_root: '源码根目录无效', unsupported_call_scope: '部分调用作用域未分析',
    target_not_found: '目标不存在', parameter_not_found: '参数不存在', duplicate_parameter: '参数名重复',
    invalid_signature: '签名不合法', unsupported_parameter_kind: '参数类型不支持',
    invalid_operation_payload: '变更配置无效', unsupported_change_type: '变更类型不支持',
    insert_before_not_found: '插入位置不存在', new_parameter_conflict: '新参数名冲突',
    parameter_name_conflict: '新参数名冲突', parameter_name_unchanged: '参数名未改变',
    invalid_parameter_name: '参数名不合法', parameter_already_required: '参数已是必填',
    syntax_error: '源码语法错误', SyntaxError: '源码语法错误', read_error: '文件读取失败',
    encoding_error: '源码编码错误', parse: '源码解析诊断', parse_diagnostics: '源码解析诊断', unsupported_scopes: '未分析的调用作用域',
    unresolved_calls: '未解析调用', unresolved_imports: '未解析导入', unresolved_references: '未解析引用',
    manual_reviews: '需要人工检查', inventory: '候选项诊断', module_inventory: '模块候选诊断',
    internal_error: '服务处理失败', analysis_failed: '分析未完成', network_error: '后端连接失败',
    validation_failed: '变更校验未通过', diagnostic: '分析诊断',
  })[code] || (REASONS[code] ? '分析范围限制' : '需要检查的诊断');
}
