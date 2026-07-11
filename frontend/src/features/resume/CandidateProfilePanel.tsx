import { Alert, Descriptions, Tag } from 'antd'
import type { Education, Project, ResumeSnapshot } from '../../api/types'
import styles from './CandidateProfilePanel.module.css'

export interface CandidateProfilePanelProps {
  snapshot: ResumeSnapshot
}

function display(value: string | null): string {
  return value?.trim() || '未识别'
}

function educationDateRange(education: Education): string {
  const start = display(education.start_date)
  const end =
    education.end_date === 'present' ? '至今' : display(education.end_date)
  return `${start} — ${end}`
}

function EducationItem({ education }: { education: Education }) {
  return (
    <li className={styles.listItem}>
      <div className={styles.itemHeading}>
        <strong>{display(education.school)}</strong>
        <span>{educationDateRange(education)}</span>
      </div>
      <p>
        {display(education.degree)} · {display(education.major)}
      </p>
    </li>
  )
}

function ProjectItem({ project }: { project: Project }) {
  return (
    <li className={styles.listItem}>
      <div className={styles.itemHeading}>
        <strong>{display(project.name)}</strong>
        <span>{display(project.role)}</span>
      </div>
      <p>{display(project.description)}</p>
      <div className={styles.tags} aria-label="项目技术栈">
        {project.technologies.length > 0 ? (
          project.technologies.map((technology) => (
            <Tag key={technology}>{technology}</Tag>
          ))
        ) : (
          <span>未识别技术栈</span>
        )}
      </div>
    </li>
  )
}

export function CandidateProfilePanel({
  snapshot,
}: CandidateProfilePanelProps) {
  const { document, profile } = snapshot

  return (
    <section className={styles.panel} aria-labelledby="candidate-profile-title">
      <div className={styles.heading}>
        <div>
          <p className={styles.kicker}>第二步</p>
          <h2 id="candidate-profile-title">候选人档案</h2>
        </div>
        {snapshot.cached && <Tag color="green">解析缓存命中</Tag>}
      </div>

      {snapshot.degraded && (
        <Alert
          showIcon
          type="info"
          title="AI 提取暂不可用，当前档案由规则降级生成，请人工核对。"
        />
      )}

      <Descriptions column={3} bordered size="small">
        <Descriptions.Item label="姓名">{display(profile.name)}</Descriptions.Item>
        <Descriptions.Item label="电话">{display(profile.phone)}</Descriptions.Item>
        <Descriptions.Item label="邮箱">{display(profile.email)}</Descriptions.Item>
        <Descriptions.Item label="所在地">{display(profile.address)}</Descriptions.Item>
        <Descriptions.Item label="求职意向">
          {display(profile.job_intention)}
        </Descriptions.Item>
        <Descriptions.Item label="期望薪资">
          {display(profile.expected_salary)}
        </Descriptions.Item>
        <Descriptions.Item label="工作年限">
          {profile.years_of_experience === null
            ? '未识别'
            : `${profile.years_of_experience} 年`}
        </Descriptions.Item>
        <Descriptions.Item label="文件名">{document.filename}</Descriptions.Item>
        <Descriptions.Item label="页数">{document.page_count} 页</Descriptions.Item>
        <Descriptions.Item label="字符数">
          {document.character_count.toLocaleString('zh-CN')}
        </Descriptions.Item>
      </Descriptions>

      <section className={styles.detailSection} aria-labelledby="education-title">
        <h3 id="education-title">教育经历</h3>
        {profile.education.length > 0 ? (
          <ul className={styles.list}>
            {profile.education.map((education, index) => (
              <EducationItem key={`${education.school ?? 'education'}-${index}`} education={education} />
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>未识别教育经历</p>
        )}
      </section>

      <section className={styles.detailSection} aria-labelledby="projects-title">
        <h3 id="projects-title">项目经历</h3>
        {profile.projects.length > 0 ? (
          <ul className={styles.list}>
            {profile.projects.map((project, index) => (
              <ProjectItem key={`${project.name ?? 'project'}-${index}`} project={project} />
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>未识别项目经历</p>
        )}
      </section>
    </section>
  )
}
