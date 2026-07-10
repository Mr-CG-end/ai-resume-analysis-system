import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('应用首页', () => {
  it('展示产品名称、分析流程和可访问的上传占位操作', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: '智能简历分析系统',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('上传简历')).toBeInTheDocument()
    expect(screen.getByText('提取信息')).toBeInTheDocument()
    expect(screen.getByText('岗位匹配')).toBeInTheDocument()

    expect(
      screen.getByRole('button', {
        name: '上传 PDF 简历（下一步实现）',
      }),
    ).toBeDisabled()
  })
})
