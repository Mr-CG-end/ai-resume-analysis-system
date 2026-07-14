import type { MatchResponse, ResumeSnapshot } from '../api/types'

export const resumeSnapshotFixture: ResumeSnapshot = {
  resume_id: 'res_550e8400-e29b-41d4-a716-446655440000',
  document: {
    filename: '候选人简历.pdf',
    page_count: 2,
    character_count: 47,
  },
  cleaned_text: '张三，Python 后端工程师。负责简历解析与匹配服务，使用 FastAPI 和 Redis。',
  profile: {
    name: '张三',
    phone: '13800138000',
    email: 'demo@example.com',
    address: null,
    job_intention: 'Python 后端开发',
    expected_salary: null,
    years_of_experience: 2.5,
    education: [
      {
        school: '示例大学',
        degree: '本科',
        major: '计算机科学',
        start_date: '2018-09',
        end_date: '2022-06',
      },
    ],
    projects: [
      {
        name: '智能简历分析系统',
        date_range: '2024.06 - 2024.09',
        role: '后端开发',
        description: '负责简历解析与匹配服务',
        highlights: ['完成结构化信息提取与岗位匹配'],
        technologies: ['Python', 'FastAPI', 'Redis'],
      },
    ],
  },
  warnings: ['address_not_found', 'expected_salary_not_found'],
  degraded: false,
  cached: false,
}

export const matchResponseFixture: MatchResponse = {
  match_id: 'mat_550e8400-e29b-41d4-a716-446655440001',
  resume_id: resumeSnapshotFixture.resume_id,
  jd_keywords: ['Python', 'RESTful API', 'Redis', 'Serverless'],
  matched_keywords: ['Python', 'Redis'],
  missing_keywords: ['RESTful API', 'Serverless'],
  responsibility_keywords: ['后端开发', '接口开发'],
  matched_responsibilities: ['后端开发'],
  missing_responsibilities: ['接口开发'],
  scores: {
    skill_match: 50,
    experience_relevance: 80,
    overall: 62,
  },
  evidence: [
    {
      dimension: 'experience',
      text: '负责简历解析与匹配服务',
    },
  ],
  summary: '技能覆盖部分岗位要求，项目经历与岗位职责相关。',
  method: 'hybrid',
  warnings: [],
  degraded: false,
  cached: false,
}
