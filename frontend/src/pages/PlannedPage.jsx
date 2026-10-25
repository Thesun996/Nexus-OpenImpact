export default function PlannedPage({ navigate }) {
  return (
    <>
      <section className="page-heading"><div><h1>功能规划中</h1><p>第一版优先完成项目上传、函数选择、变更配置和影响报告。</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={() => navigate('upload')}>返回核心流程</button></div></section>
      <section className="detail-card empty-state-card"><div className="empty-state-icon">⌬</div><h2>这个模块暂未接入</h2><p>依赖分析和配置管理仍是预留位置；代码关系图已接入，可查看 Python 函数的静态调用关系。历史报告已有本机 SQLite 的基础保存与读取页面，但还不是账号级报告中心。</p><div className="empty-state-actions"><button className="primary-action" type="button" onClick={() => navigate('functions')}>选择函数</button><button className="ghost-action" type="button" onClick={() => navigate('history')}>查看历史报告</button><button className="ghost-action" type="button" onClick={() => navigate('report')}>查看当前报告</button></div></section>
    </>
  );
}
