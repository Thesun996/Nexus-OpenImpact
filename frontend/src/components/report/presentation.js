// Formatting only. Evidence identity and slot checks stay in pages/reportData.js.
export function entries(value) {
  return Array.isArray(value) ? value : [];
}

export function locationText(location) {
  if (!location?.file) return '位置未提供';
  const line = location.line != null ? `:${location.line}` : '';
  const column = location.column != null ? `:${location.column}` : '';
  return `${location.file}${line}${column}`;
}

export function findingLocation(finding) {
  if (finding?.impact_type === 'direct') return finding;
  // Keep the existing shortest-source representative used by Core and the UI.
  const representative = entries(finding?.sources).reduce((shortest, source) =>
    !shortest || entries(source.propagation_path).length < entries(shortest.propagation_path).length ? source : shortest, null);
  return representative?.propagation_path?.[0];
}

export function impactLabel(type) {
  return type === 'direct' ? '直接影响' : type === 'indirect_1hop' ? '1 层间接影响'
    : type === 'indirect_2hop' ? '2 层间接影响' : '其他影响记录';
}

export function callScopeHint(symbol) {
  if (symbol?.includes('<class_body@')) return '这是类定义体中的调用，通常在执行类定义时发生；它与实例方法调用不同。';
  if (symbol?.includes('<lambda@')) return '这是匿名函数体中的调用；是否及何时执行仍需结合实际调用方式检查，没有据此推测外层调用路径。';
  return null;
}

export { statusLabel, riskLabel, reasonLabel, ruleLabel } from '../../presentation/labels.js';
