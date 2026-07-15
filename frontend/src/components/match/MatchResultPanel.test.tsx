import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { matchResponseFixture } from '../../test/fixtures'
import { MatchResultPanel } from './MatchResultPanel'

afterEach(cleanup)

describe('MatchResultPanel', () => {
  it('展示服务端分数、关键词、摘要和原文证据', () => {
    render(<MatchResultPanel result={matchResponseFixture} onReset={vi.fn()} />)

    expect(screen.getByLabelText('综合匹配分数 62 分')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
    expect(screen.getByText('80')).toBeInTheDocument()
    expect(screen.getByText('技能匹配率（60% 权重）')).toBeInTheDocument()
    expect(screen.getByText('经历相关性（40% 权重）')).toBeInTheDocument()
    expect(screen.getByText(matchResponseFixture.summary)).toBeInTheDocument()
    expect(screen.getByText('已匹配：Python')).toBeInTheDocument()
    expect(screen.getByText('待补充：Serverless')).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('负责简历解析与匹配服务')
    expect(screen.getByText('规则已识别职责')).toBeInTheDocument()
    expect(screen.getByText('规则未检出职责证据')).toBeInTheDocument()
    expect(screen.getByText('已识别：后端开发')).toBeInTheDocument()
    expect(screen.getByText('未检出：接口开发')).toBeInTheDocument()
    expect(
      screen.getByText(
        '技能和职责标签根据简历原文规则识别；经历相关性分数由 AI 结合原文证据评估。',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('AI + 规则综合评分')).toBeInTheDocument()
    expect(screen.queryByText('AI 经历精评未完成')).not.toBeInTheDocument()
  })

  it('仅在缓存命中时显示轻量标识', () => {
    const { rerender } = render(
      <MatchResultPanel result={matchResponseFixture} onReset={vi.fn()} />,
    )
    expect(screen.queryByText('缓存命中')).not.toBeInTheDocument()

    rerender(
      <MatchResultPanel
        result={{ ...matchResponseFixture, cached: true }}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByText('缓存命中')).toBeInTheDocument()
  })

  it('降级时明确说明规则评分且不伪造证据', () => {
    render(
      <MatchResultPanel
        result={{
          ...matchResponseFixture,
          method: 'rule_fallback',
          degraded: true,
          warnings: ['ai_matching_fallback'],
          evidence: [],
        }}
        onReset={vi.fn()}
      />,
    )

    expect(screen.getByText('规则回退评分')).toBeInTheDocument()
    expect(screen.getByText('AI 经历精评未完成')).toBeInTheDocument()
    expect(
      screen.getByText('本次 AI 证据未通过原文验证，未展示可能失真的内容。'),
    ).toBeInTheDocument()
    const evidenceSection = screen.getByRole('heading', { name: 'AI 经历相关性原文证据' }).parentElement!
    expect(within(evidenceSection).queryByRole('list')).not.toBeInTheDocument()
  })

  it('关键词组为空时显示可读缺省状态', () => {
    render(
      <MatchResultPanel
        result={{ ...matchResponseFixture, matched_keywords: [], missing_keywords: [] }}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getAllByText('未提取到')).toHaveLength(2)
  })

  it('触发重新分析', () => {
    const onReset = vi.fn()
    render(<MatchResultPanel result={matchResponseFixture} onReset={onReset} />)
    fireEvent.click(screen.getByRole('button', { name: '重新分析' }))
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})
