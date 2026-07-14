import { Alert, Button, Progress, Statistic, Tag } from 'antd'
import type { MatchResponse } from '../../api/types'
import styles from './MatchResultPanel.module.css'

export interface MatchResultPanelProps {
  result: MatchResponse
  onReset: () => void
}

interface KeywordGroupProps {
  title: string
  keywords: string[]
  tone: 'matched' | 'missing'
}

function KeywordGroup({ title, keywords, tone }: KeywordGroupProps) {
  return (
    <section className={styles.keywordGroup} aria-label={title}>
      <h3>{title}</h3>
      <div className={styles.tags}>
        {keywords.length === 0 ? (
          <span className={styles.empty}>未提取到</span>
        ) : (
          keywords.map((keyword) => (
            <Tag key={keyword} color={tone === 'matched' ? 'success' : 'default'}>
              {tone === 'matched' ? '已匹配：' : '待补充：'}{keyword}
            </Tag>
          ))
        )}
      </div>
    </section>
  )
}

export function MatchResultPanel({ result, onReset }: MatchResultPanelProps) {
  const isFallback = result.degraded || result.method === 'rule_fallback'

  return (
    <section className={styles.panel} aria-labelledby="match-result-title">
      <div className={styles.heading}>
        <div>
          <p className={styles.kicker}>匹配结果</p>
          <h2 id="match-result-title">候选人与岗位的契合度</h2>
        </div>
        <div className={styles.statusTags}>
          <Tag color={isFallback ? 'gold' : 'green'}>
            {isFallback ? '规则回退评分' : 'AI + 规则综合评分'}
          </Tag>
          {result.cached && <Tag>缓存命中</Tag>}
        </div>
      </div>

      {isFallback && (
        <Alert
          className={styles.alert}
          type="warning"
          showIcon
          title="AI 经历精评未完成"
          description="模型未能返回可验证的简历原文证据。技能分仍按关键词匹配计算，经历分暂按职责关键词覆盖率计算。"
        />
      )}

      <div className={styles.scoreGrid}>
        <div className={styles.overallScore}>
          <Progress
            type="circle"
            percent={result.scores.overall}
            size={148}
            strokeColor="#287a5d"
            aria-label={`综合匹配分数 ${result.scores.overall} 分`}
          />
          <span>综合匹配分数</span>
        </div>
        <div className={styles.breakdown}>
          <Statistic title="技能匹配率（60% 权重）" value={result.scores.skill_match} suffix="分" />
          <Statistic
            title="经历相关性（40% 权重）"
            value={result.scores.experience_relevance}
            suffix="分"
          />
        </div>
      </div>

      <div className={styles.summary}>
        <h3>分析摘要</h3>
        <p>{result.summary}</p>
      </div>

      <section aria-labelledby="keyword-analysis-title">
        <h3 id="keyword-analysis-title" className={styles.sectionTitle}>岗位关键词分析</h3>
        <div className={styles.keywordGrid}>
          <KeywordGroup title="已匹配技能" keywords={result.matched_keywords} tone="matched" />
          <KeywordGroup title="待补充技能" keywords={result.missing_keywords} tone="missing" />
          <KeywordGroup title="已覆盖职责" keywords={result.matched_responsibilities} tone="matched" />
          <KeywordGroup title="待补充职责" keywords={result.missing_responsibilities} tone="missing" />
        </div>
      </section>

      <section className={styles.evidence} aria-labelledby="evidence-title">
        <h3 id="evidence-title">AI 经历相关性原文证据</h3>
        {result.evidence.length > 0 ? (
          <ul>
            {result.evidence.map((item, index) => (
              <li key={`${item.text}-${index}`}>{item.text}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.emptyEvidence}>
            {isFallback
              ? '本次 AI 证据未通过原文验证，未展示可能失真的内容。'
              : '未提取到可展示的原文证据。'}
          </p>
        )}
      </section>

      <Button type="primary" onClick={onReset}>
        重新分析
      </Button>
    </section>
  )
}
