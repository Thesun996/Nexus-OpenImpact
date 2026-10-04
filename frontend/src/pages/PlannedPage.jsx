export default function PlannedPage({ navigate }) {
  return (
    <>
      <section className="page-heading"><div><h1>功能规划中</h1><p>第一版优先完成项目上传、函数选择、变更配置和影响报告。</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={() => navigate('upload')}>返回核心流程</button></div></section>
      <section className="detail-card empty-state-card"><div className="empty-state-icon">⌬</div><h2>这个模块暂未接入</h2><p>调用图可视化、依赖分析、历史记录与配置管理当前保留导航位置。本轮完成 React 工程化，现有核心流程可在演示模式下预览。</p><div className="empty-state-actions"><button className="primary-action" type="button" onClick={() => navigate('functions')}>选择函数</button><button className="ghost-action" type="button" onClick={() => navigate('report')}>查看当前报告</button></div></section>
    </>
  );
}
