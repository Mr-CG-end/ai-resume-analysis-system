import { Button, Form, Input } from 'antd'
import { useState, type FormEvent } from 'react'
import styles from './JobMatchForm.module.css'

const MIN_JD_LENGTH = 20
const MAX_JD_LENGTH = 10_000

export interface JobMatchFormProps {
  jobDescription: string
  onJobDescriptionChange: (value: string) => void
  onSubmit: () => void
  onReset: () => void
  disabled?: boolean
  submitting?: boolean
  hasSnapshot: boolean
}

function validationMessage(length: number): string | undefined {
  if (length < MIN_JD_LENGTH) return '岗位描述至少需要 20 个字符'
  if (length > MAX_JD_LENGTH) return '岗位描述不能超过 10,000 个字符'
  return undefined
}

export function JobMatchForm({
  jobDescription,
  onJobDescriptionChange,
  onSubmit,
  onReset,
  disabled = false,
  submitting = false,
  hasSnapshot,
}: JobMatchFormProps) {
  const [showValidation, setShowValidation] = useState(false)
  const trimmedLength = jobDescription.trim().length
  const error = validationMessage(trimmedLength)
  const visibleError = showValidation ? error : undefined
  const cannotSubmit = disabled || submitting || !hasSnapshot || Boolean(error)
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (error) {
      setShowValidation(true)
      return
    }
    if (!cannotSubmit) onSubmit()
  }

  return (
    <section className={styles.panel} aria-labelledby="job-match-title">
      <div className={styles.heading}>
        <div>
          <p className={styles.kicker}>岗位匹配</p>
          <h2 id="job-match-title">填写岗位要求</h2>
        </div>
        <Button type="text" onClick={onReset} disabled={submitting}>
          重新分析
        </Button>
      </div>

      <Form
        layout="vertical"
        onSubmitCapture={handleSubmit}
        aria-describedby="job-description-help"
      >
        <Form.Item
          label="岗位描述"
          htmlFor="job-description"
          validateStatus={visibleError ? 'error' : undefined}
          help={visibleError ? <span role="alert">{visibleError}</span> : undefined}
        >
          <Input.TextArea
            id="job-description"
            value={jobDescription}
            onChange={(event) => onJobDescriptionChange(event.target.value)}
            onBlur={() => setShowValidation(true)}
            disabled={disabled || submitting}
            rows={7}
            placeholder="例如：招聘 Python 后端工程师，需要 FastAPI、Redis 和 RESTful API 项目经验。"
            aria-describedby="job-description-help"
            aria-invalid={Boolean(visibleError)}
            aria-label="岗位描述"
          />
        </Form.Item>

        <div id="job-description-help" className={styles.helpRow}>
          <span>请粘贴 20–10,000 个字符的完整岗位描述。</span>
          <span className={visibleError ? styles.countError : undefined}>
            {trimmedLength.toLocaleString('zh-CN')} / 10,000
          </span>
        </div>

        <div className={styles.actions}>
          <Button
            type="primary"
            htmlType="submit"
            size="large"
            loading={submitting}
            disabled={cannotSubmit}
            aria-label={submitting ? '正在匹配…' : '开始匹配'}
          >
            {submitting ? '正在匹配…' : '开始匹配'}
          </Button>
          {!hasSnapshot && (
            <span className={styles.snapshotHint}>请先解析简历，再进行岗位匹配。</span>
          )}
        </div>
        <div className={styles.liveStatus} aria-live="polite">
          {submitting ? '正在分析岗位与候选人的匹配度。' : ''}
        </div>
      </Form>
    </section>
  )
}
