import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { resumeSnapshotFixture } from '../../test/fixtures'
import type { ResumeSnapshot } from '../../api/types'
import { CandidateProfilePanel } from './CandidateProfilePanel'

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

function snapshot(overrides: Partial<ResumeSnapshot> = {}): ResumeSnapshot {
  return { ...resumeSnapshotFixture, ...overrides }
}

describe('CandidateProfilePanel', () => {
  it('shows candidate fields, document metadata, education and projects', () => {
    render(<CandidateProfilePanel snapshot={resumeSnapshotFixture} />)

    expect(screen.getByRole('heading', { name: '候选人档案' })).toBeInTheDocument()
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('2.5 年')).toBeInTheDocument()
    expect(screen.getByText('候选人简历.pdf')).toBeInTheDocument()
    expect(screen.getByText('示例大学')).toBeInTheDocument()
    expect(screen.getByText('智能简历分析系统')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.queryByText(resumeSnapshotFixture.cleaned_text)).not.toBeInTheDocument()
  })

  it('uses explicit empty values and preserves zero years of experience', () => {
    render(
      <CandidateProfilePanel
        snapshot={snapshot({
          profile: {
            ...resumeSnapshotFixture.profile,
            name: '   ',
            phone: null,
            years_of_experience: 0,
            education: [],
            projects: [],
          },
        })}
      />,
    )

    expect(screen.getAllByText('未提取到').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('0 年')).toBeInTheDocument()
    expect(screen.getByText('未提取到教育经历')).toBeInTheDocument()
    expect(screen.getByText('未提取到项目经历')).toBeInTheDocument()
  })

  it('renders present dates and an empty technology state', () => {
    render(
      <CandidateProfilePanel
        snapshot={snapshot({
          profile: {
            ...resumeSnapshotFixture.profile,
            education: [
              {
                school: null,
                degree: null,
                major: null,
                start_date: null,
                end_date: 'present',
              },
            ],
            projects: [
              {
                name: null,
                date_range: null,
                role: null,
                description: null,
                highlights: [],
                technologies: [],
              },
            ],
          },
        })}
      />,
    )

    expect(screen.getByText(/时间未注明 — 至今/)).toBeInTheDocument()
    expect(screen.getByText('未提取到技术栈')).toBeInTheDocument()
  })

  it('shows degradation and cache state independently', () => {
    const { rerender } = render(
      <CandidateProfilePanel snapshot={snapshot({ degraded: true, cached: false })} />,
    )
    expect(
      screen.getByText('AI 提取暂不可用，当前档案由规则降级生成，请人工核对。'),
    ).toBeInTheDocument()
    expect(screen.queryByText('解析缓存命中')).not.toBeInTheDocument()

    rerender(<CandidateProfilePanel snapshot={snapshot({ degraded: false, cached: true })} />)
    expect(screen.getByText('解析缓存命中')).toBeInTheDocument()
    expect(screen.queryByText(/规则降级生成/)).not.toBeInTheDocument()
  })
})
