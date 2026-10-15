export function buildReportDownload(report, { projectName, reportId, mode = 'project' } = {}) {
  if (!report || typeof report !== 'object' || Array.isArray(report)) throw new Error('没有可下载的报告。');
  const name = String(projectName || report.project_name || 'report').normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-').slice(0, 64).replace(/^[.-]+|[.-]+$/g, '') || 'report';
  const identity = String(reportId || report.project_fingerprint || '').replace(/[^a-zA-Z0-9]/g, '').slice(0, 16);
  return {
    filename: `openimpact-${mode === 'demo' ? 'demo-' : ''}${name}${identity ? `-${identity}` : ''}.json`,
    content: `${JSON.stringify(report, null, 2)}\n`,
  };
}

export function downloadReport(report, options) {
  const { filename, content } = buildReportDownload(report, options);
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }));
  let anchor;
  try {
    anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
  } finally {
    anchor?.remove();
    // Give the browser time to consume the URL before releasing its memory.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
