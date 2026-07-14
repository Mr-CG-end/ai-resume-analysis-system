export type ResumeWarningCode =
  | 'name_not_found'
  | 'phone_not_found'
  | 'email_not_found'
  | 'address_not_found'
  | 'job_intention_not_found'
  | 'expected_salary_not_found'
  | 'years_of_experience_uncertain'
  | 'ai_extraction_fallback'

export interface DocumentMetadata {
  filename: string
  page_count: number
  character_count: number
}

export interface Education {
  school: string | null
  degree: string | null
  major: string | null
  start_date: string | null
  end_date: string | null
}

export interface Project {
  name: string | null
  date_range: string | null
  role: string | null
  description: string | null
  highlights: string[]
  technologies: string[]
}

export interface CandidateProfile {
  name: string | null
  phone: string | null
  email: string | null
  address: string | null
  job_intention: string | null
  expected_salary: string | null
  years_of_experience: number | null
  education: Education[]
  projects: Project[]
}

export interface ResumeSnapshot {
  resume_id: string
  document: DocumentMetadata
  cleaned_text: string
  profile: CandidateProfile
  warnings: ResumeWarningCode[]
  degraded: boolean
  cached: boolean
}

export interface MatchRequest {
  resume_snapshot: ResumeSnapshot
  job_description: string
}

export interface ScoreBreakdown {
  skill_match: number
  experience_relevance: number
  overall: number
}

export interface MatchEvidence {
  dimension: 'experience'
  text: string
}

export type MatchMethod = 'hybrid' | 'rule_fallback'
export type MatchWarningCode = 'ai_matching_fallback'

export interface MatchResponse {
  match_id: string
  resume_id: string
  jd_keywords: string[]
  matched_keywords: string[]
  missing_keywords: string[]
  responsibility_keywords: string[]
  matched_responsibilities: string[]
  missing_responsibilities: string[]
  scores: ScoreBreakdown
  evidence: MatchEvidence[]
  summary: string
  method: MatchMethod
  warnings: MatchWarningCode[]
  degraded: boolean
  cached: boolean
}

export interface ErrorDetail {
  code: string
  message: string
  request_id: string
  details: Record<string, unknown>
}

export interface ErrorResponse {
  error: ErrorDetail
}
