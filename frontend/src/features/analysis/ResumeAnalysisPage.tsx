import { Alert, Button, Steps, Tag } from 'antd'
import { lazy, Suspense, useEffect, useReducer, useRef } from 'react'
import { ApiError, createMatch, createResume } from '../../api/client'
import type { MatchResponse, ResumeSnapshot } from '../../api/types'
import { ResumeUpload } from '../resume/ResumeUpload'
import type { UploadValidationError } from '../resume/resumeValidation'
import styles from './ResumeAnalysisPage.module.css'

const CandidateProfilePanel = lazy(() =>
  import('../resume/CandidateProfilePanel').then((module) => ({
    default: module.CandidateProfilePanel,
  })),
)
const JobMatchForm = lazy(() =>
  import('../../components/match/JobMatchForm').then((module) => ({
    default: module.JobMatchForm,
  })),
)
const MatchResultPanel = lazy(() =>
  import('../../components/match/MatchResultPanel').then((module) => ({
    default: module.MatchResultPanel,
  })),
)

type WorkflowStatus = 'idle' | 'parsing' | 'ready' | 'matching'

interface UiError {
  title: string
  description: string
  requestId: string | null
}

interface State {
  status: WorkflowStatus
  file: File | null
  snapshot: ResumeSnapshot | null
  jobDescription: string
  result: MatchResponse | null
  error: UiError | null
}

type Action =
  | { type: 'file'; file: File | null }
  | { type: 'parsing' }
  | { type: 'parsed'; snapshot: ResumeSnapshot }
  | { type: 'job'; value: string }
  | { type: 'matching' }
  | { type: 'matched'; result: MatchResponse }
  | { type: 'error'; error: UiError }
  | { type: 'clearError' }
  | { type: 'reset' }

const initialState: State = {
  status: 'idle',
  file: null,
  snapshot: null,
  jobDescription: '',
  result: null,
  error: null,
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'file':
      return { ...initialState, file: action.file }
    case 'parsing':
      return { ...state, status: 'parsing', snapshot: null, result: null, error: null }
    case 'parsed':
      return { ...state, status: 'ready', snapshot: action.snapshot, error: null }
    case 'job':
      return { ...state, jobDescription: action.value, result: null, error: null }
    case 'matching':
      return { ...state, status: 'matching', result: null, error: null }
    case 'matched':
      return { ...state, status: 'ready', result: action.result, error: null }
    case 'error':
      return {
        ...state,
        status: state.snapshot ? 'ready' : 'idle',
        error: action.error,
      }
    case 'clearError':
      return { ...state, error: null }
    case 'reset':
      return initialState
  }
}

const errorMessages: Record<string, { title: string; description: string }> = {
  PDF_NO_EXTRACTABLE_TEXT: {
    title: '无法读取这份简历',
    description: '请上传包含可选择文字的 PDF，扫描图片暂不支持。',
  },
  PDF_ENCRYPTED: {
    title: 'PDF 已加密',
    description: '请先移除文件密码，再重新上传。',
  },
  PDF_CORRUPTED: {
    title: 'PDF 文件损坏',
    description: '请重新导出 PDF 或选择另一份文件。',
  },
  PDF_PAGE_LIMIT_EXCEEDED: {
    title: 'PDF 页数过多',
    description: '请将简历精简到 30 页以内后重试。',
  },
  PDF_TEXT_TOO_LONG: {
    title: '简历文本过长',
    description: '请精简简历内容后重新上传。',
  },
  JD_KEYWORDS_NOT_FOUND: {
    title: '没有识别到岗位关键词',
    description: '请补充岗位技能、职责或技术栈后重新匹配。',
  },
  INVALID_RESUME_SNAPSHOT: {
    title: '简历档案已失效',
    description: '请重新上传并解析简历。',
  },
  NETWORK_ERROR: {
    title: '无法连接分析服务',
    description: '请检查网络连接或稍后重试。',
  },
}

function apiErrorToUi(error: unknown): UiError {
  if (error instanceof ApiError) {
    const mapped = errorMessages[error.code]
    return {
      title: mapped?.title ?? '分析未完成',
      description: mapped?.description ?? error.message,
      requestId: error.requestId,
    }
  }
  return {
    title: '分析未完成',
    description: '发生未知错误，请稍后重试。',
    requestId: null,
  }
}

function validationErrorToUi(error: UploadValidationError): UiError {
  return { title: '文件不符合要求', description: error.message, requestId: null }
}

export function ResumeAnalysisPage() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const requestRef = useRef<AbortController | null>(null)

  useEffect(() => () => requestRef.current?.abort(), [])

  const abortActiveRequest = () => {
    requestRef.current?.abort()
    requestRef.current = null
  }

  const reset = () => {
    abortActiveRequest()
    dispatch({ type: 'reset' })
  }

  const parseResume = async () => {
    if (!state.file || state.status === 'parsing') return
    abortActiveRequest()
    const controller = new AbortController()
    requestRef.current = controller
    dispatch({ type: 'parsing' })
    try {
      const snapshot = await createResume(state.file, { signal: controller.signal })
      if (!controller.signal.aborted) dispatch({ type: 'parsed', snapshot })
    } catch (error) {
      if (!controller.signal.aborted) {
        dispatch({ type: 'error', error: apiErrorToUi(error) })
      }
    } finally {
      if (requestRef.current === controller) requestRef.current = null
    }
  }

  const matchResume = async () => {
    if (!state.snapshot || state.status === 'matching') return
    abortActiveRequest()
    const controller = new AbortController()
    requestRef.current = controller
    dispatch({ type: 'matching' })
    try {
      const result = await createMatch(
        {
          resume_snapshot: state.snapshot,
          job_description: state.jobDescription.trim(),
        },
        { signal: controller.signal },
      )
      if (!controller.signal.aborted) dispatch({ type: 'matched', result })
    } catch (error) {
      if (!controller.signal.aborted) {
        dispatch({ type: 'error', error: apiErrorToUi(error) })
      }
    } finally {
      if (requestRef.current === controller) requestRef.current = null
    }
  }

  const step = state.result ? 2 : state.snapshot ? 1 : 0

  return (
    <main className={styles.shell}>
      <div className={styles.workspace}>
        <header className={styles.hero}>
          <div>
            <p className={styles.eyebrow}>候选人评估工作台</p>
            <h1 aria-label="智能简历分析系统">
              <span>智能简历</span>
              <span>分析系统</span>
            </h1>
            <p className={styles.intro}>
              从简历信息提取到岗位匹配，用可定位的证据辅助每一次判断。
            </p>
          </div>
          <div className={styles.privacyNote}>
            <span>单次分析</span>
            <strong>文件不会作为历史记录保存</strong>
          </div>
        </header>

        <nav className={styles.steps} aria-label="分析进度">
          <Steps
            current={step}
            responsive
            items={[
              { title: '上传简历', content: '选择文本型 PDF' },
              { title: '确认档案', content: '核对候选人信息' },
              { title: '岗位匹配', content: '查看分数与证据' },
            ]}
          />
        </nav>

        <div className={styles.content}>
          {(state.status === 'parsing' || state.status === 'matching') && (
            <Alert
              type="info"
              showIcon
              title={state.status === 'parsing' ? '正在解析简历' : '正在分析岗位匹配度'}
              description="可以取消当前请求并从头开始，不会保留本次输入。"
              action={<Button onClick={reset}>取消并重新分析</Button>}
            />
          )}

          {state.error && (
            <Alert
              type="error"
              showIcon
              title={state.error.title}
              description={
                <div className={styles.errorBody}>
                  <span>{state.error.description}</span>
                  {state.error.requestId && (
                    <span className={styles.requestId}>请求编号：{state.error.requestId}</span>
                  )}
                </div>
              }
              action={
                <Button size="small" onClick={() => dispatch({ type: 'clearError' })}>
                  关闭
                </Button>
              }
            />
          )}

          <ResumeUpload
            file={state.file}
            parsing={state.status === 'parsing'}
            disabled={state.status === 'matching'}
            onFileChange={(file) => {
              abortActiveRequest()
              dispatch({ type: 'file', file })
            }}
            onParse={() => void parseResume()}
            onValidationError={(error) =>
              dispatch(error ? { type: 'error', error: validationErrorToUi(error) } : { type: 'clearError' })
            }
          />

          <Suspense
            fallback={
              <div className={styles.lazyFallback} role="status" aria-live="polite">
                正在加载分析界面…
              </div>
            }
          >
            {state.snapshot && <CandidateProfilePanel snapshot={state.snapshot} />}

            {state.snapshot && (
              <JobMatchForm
                jobDescription={state.jobDescription}
                onJobDescriptionChange={(value) => dispatch({ type: 'job', value })}
                onSubmit={() => void matchResume()}
                onReset={reset}
                disabled={state.status === 'parsing'}
                submitting={state.status === 'matching'}
                hasSnapshot
              />
            )}

            {state.result && <MatchResultPanel result={state.result} onReset={reset} />}
          </Suspense>

          {(state.snapshot?.degraded || state.result?.degraded) && (
            <div className={styles.footerNote}>
              <Tag color="gold">需人工核对</Tag>
              降级结果仍可用于初步筛选，但不应替代招聘人员判断。
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
