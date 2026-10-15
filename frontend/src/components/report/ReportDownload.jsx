import { useState } from 'react';
import { downloadReport } from '../../pages/reportDownload.js';

export default function ReportDownload({ report, projectName, reportId, mode, disabled = false }) {
  const [failure, setFailure] = useState(null);
  function download() {
    setFailure(null);
    try { downloadReport(report, { projectName, reportId, mode }); }
    catch { setFailure({ report, message: '无法下载报告，请重试。' }); }
  }
  return <div className="oi-report-download">
    <button className="ghost-action" type="button" onClick={download} disabled={!report || disabled}>下载 JSON</button>
    {failure && failure.report === report && <span role="alert">{failure.message}</span>}
  </div>;
}
