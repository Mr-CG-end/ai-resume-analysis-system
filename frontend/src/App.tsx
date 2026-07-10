import './App.css'

const analysisSteps = [
  {
    number: '01',
    title: '上传简历',
    description: '选择一份文本型 PDF 简历。',
  },
  {
    number: '02',
    title: '提取信息',
    description: '识别候选人档案与关键经历。',
  },
  {
    number: '03',
    title: '岗位匹配',
    description: '结合岗位要求给出可解释结果。',
  },
] as const

function App() {
  return (
    <main className="app-shell">
      <article className="workspace" aria-labelledby="product-title">
        <header className="hero">
          <p className="eyebrow">候选人评估工作台</p>
          <h1 id="product-title">智能简历分析系统</h1>
          <p className="hero-description">
            从简历信息提取到岗位匹配，用清晰证据辅助每一次判断。
          </p>
        </header>

        <section className="flow" aria-labelledby="flow-title">
          <div className="section-heading">
            <p className="section-kicker">工作流程</p>
            <h2 id="flow-title">三步完成分析</h2>
          </div>

          <ol className="step-list">
            {analysisSteps.map((step) => (
              <li key={step.number} className="step-item">
                <span className="step-number" aria-hidden="true">
                  {step.number}
                </span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="next-step" aria-labelledby="next-step-title">
          <div>
            <p className="section-kicker">下一步</p>
            <h2 id="next-step-title">准备上传简历</h2>
            <p>PDF 上传功能将在后续任务中实现，当前操作暂不可用。</p>
          </div>
          <button type="button" disabled>
            上传 PDF 简历（下一步实现）
          </button>
        </section>
      </article>
    </main>
  )
}

export default App
