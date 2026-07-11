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
          <span className={styles.empty}>暂无</span>
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
            {isFallback ? '规则评分' : '综合分析'}
          </Tag>
          {result.cached && <Tag>缓存命中</Tag>}
        </div>
      </div>

      {isFallback && (
        <Alert
          className={styles.alert}
          type="warning"
          showIcon
          title="AI 经历分析暂不可用"
          description="本次结果采用规则评分，可继续查看并作为参考。"
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
          <Statistic title="技能匹配（60% 权重）" value={result.scores.skill_match} suffix="分" />
          <Statistic
            title="经历相关（40% 权重）"
            value={result.scores.experience_relevance}
            suffix="分"
          />
        </div>
      </div>

      <div className={styles.summary}>
        <h3>分析摘要</h3>
        <p>{result.summary}</p>
      </div>

      <div className={styles.keywordGrid}>
        <KeywordGroup title="已匹配关键词" keywords={result.matched_keywords} tone="matched" />
        <KeywordGroup title="待补充关键词" keywords={result.missing_keywords} tone="missing" />
      </div>

      <section className={styles.evidence} aria-labelledby="evidence-title">
        <h3 id="evidence-title">简历原文证据</h3>
        {result.evidence.length > 0 ? (
          <ul>
            {result.evidence.map((item, index) => (
              <li key={`${item.text}-${index}`}>{item.text}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.emptyEvidence}>
            {isFallback ? '规则降级结果不包含 AI 经历证据。' : '暂无可展示的原文证据。'}
          </p>
        )}
      </section>

      <Button type="primary" onClick={onReset}>
        重新分析
      </Button>
    </section>
  )
}
