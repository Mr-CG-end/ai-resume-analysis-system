import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const resumeFixture = fileURLToPath(
  new URL('../../../backend/tests/fixtures/resume-valid-3-pages.pdf', import.meta.url),
)

test('recruiter completes the cross-origin fallback workflow', async ({ page }) => {
  const consoleErrors: string[] = []
  const apiUrls: string[] = []
  const requestIds: string[] = []
  const cachedValues: boolean[] = []

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('response', async (response) => {
    const url = new URL(response.url())
    if (!['/api/v1/resumes', '/api/v1/matches'].includes(url.pathname)) return
    apiUrls.push(response.url())
    const requestId = response.headers()['x-request-id']
    if (requestId) requestIds.push(requestId)
    const payload = (await response.json()) as { cached?: unknown }
    if (typeof payload.cached === 'boolean') cachedValues.push(payload.cached)
  })

  await page.goto('/')
  const fileInput = page.locator('input[type="file"]')

  await fileInput.setInputFiles({
    name: 'not-a-resume.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not a pdf'),
  })
  await expect(page.getByText('文件不符合要求')).toBeVisible()
  expect(apiUrls).toHaveLength(0)

  await fileInput.setInputFiles(resumeFixture)
  await page.getByRole('button', { name: '解析简历' }).click()
  await expect(page.getByRole('heading', { name: '候选人档案' })).toBeVisible()
  await expect(page.getByText('AI 提取暂不可用')).toBeVisible()

  const jobDescription = page.getByLabel('岗位描述')
  await jobDescription.fill('招聘 Python 后端工程师，需要 FastAPI、Redis、Docker 和 RESTful API 项目经验。')
  await page.getByRole('button', { name: '开始匹配' }).click()

  await expect(page.getByText('综合匹配分数')).toBeVisible()
  await expect(page.getByText('本次结果采用规则评分')).toBeVisible()
  await expect(page.getByText('规则降级结果不包含 AI 经历证据')).toBeVisible()

  expect(apiUrls).toHaveLength(2)
  expect(apiUrls.every((url) => new URL(url).origin === 'http://127.0.0.1:8000')).toBe(true)
  expect(requestIds).toHaveLength(2)
  expect(cachedValues).toEqual([false, false])

  await page.getByRole('button', { name: '重新分析' }).last().click()
  await expect(page.getByRole('heading', { name: '候选人档案' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '解析简历' })).toBeDisabled()
  expect(consoleErrors).toEqual([])
})
