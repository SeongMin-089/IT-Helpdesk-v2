export type UserRole = 'employee' | 'agent'

export interface Relation {
  id: number
  name: string
}

export interface AuthUser {
  id: number
  name: string
  partner_id: number
  partner: Relation
  role: UserRole
  groups: Record<string, boolean>
}

export interface AuthResponse {
  success: boolean
  user: AuthUser
}

export interface Ticket {
  id: number
  reference: string
  title: string
  description: string
  status: Relation | null
  priority: string
  priority_code: string
  assignee: Relation | null
  category: Relation | null
  requester: Relation | null
  closed: boolean
  active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface TicketCreateResponse {
  success: boolean
  message: string
  ticket_id: number
  auto_assigned: boolean
  assignee: Relation | null
}

export interface TicketDetailResponse {
  success: boolean
  ticket: Ticket
}

export interface TicketCategory {
  id: number
  name: string
  complete_name: string
  sequence: number
  active: boolean
  parent: Relation | null
  show_in_portal: boolean
  default_assignee: Relation | null
}

export interface TicketCategoryListResponse {
  success: boolean
  count: number
  categories: TicketCategory[]
}

export interface TicketListResponse {
  success: boolean
  count: number
  tickets: Ticket[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
}

export interface Stage {
  id: number
  name: string
  sequence: number
  closed: boolean
}

export interface StageListResponse {
  success: boolean
  count: number
  stages: Stage[]
}

export interface DashboardResponse {
  success: boolean
  summary: {
    total: number
    open: number
    closed: number
    unassigned: number
  }
  by_stage: Array<{
    id: number
    name: string
    closed: boolean
    count: number
  }>
  by_priority: Array<{
    priority: string
    label: string
    count: number
  }>
  recent_tickets: Ticket[]
}
