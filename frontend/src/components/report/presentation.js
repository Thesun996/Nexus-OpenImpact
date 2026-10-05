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

export { statusLabel, riskLabel, reasonLabel, ruleLabel } from '../../presentation/labels.js';
