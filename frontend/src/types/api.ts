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

export interface TicketUpdateResponse extends TicketDetailResponse {
  message: string
}

export type TicketCommentKind = 'comment' | 'note'

export interface TicketComment {
  id: number
  body: string
  author: Relation | null
  created_at: string | null
  kind: TicketCommentKind
  message_type: string | null
  subtype: Relation | null
}

export interface TicketCommentsResponse {
  success: boolean
  count: number
  comments: TicketComment[]
}

export interface TicketCommentCreateResponse {
  success: boolean
  message: string
  comment_id: number
  kind: TicketCommentKind
}

export interface TicketAttachment {
  id: number
  name: string
  content_type: string
  size: number
  created_at: string | null
  created_by: Relation | null
}

export interface TicketAttachmentsResponse {
  success: boolean
  count: number
  attachments: TicketAttachment[]
}

export interface TicketAttachmentUploadResponse {
  success: boolean
  message: string
  attachment: Pick<TicketAttachment, 'id' | 'name' | 'content_type' | 'size'>
}

export interface TicketHistoryField {
  id: number
  name: string
  label: string
  type: string | null
}

export interface TicketHistoryValue {
  id: number | null
  name: string | null
}

export interface TicketHistoryItem {
  id: number
  message_id: number | null
  changed_at: string | null
  changed_by: Relation | null
  change_type: 'status' | 'assignee'
  field: TicketHistoryField
  old_value: TicketHistoryValue | null
  new_value: TicketHistoryValue | null
}

export interface TicketHistoryResponse {
  success: boolean
  count: number
  history: TicketHistoryItem[]
}

export interface FaqTag {
  id: number
  name: string
}

export interface Faq {
  id: number
  name: string
  content: string
  tags: FaqTag[]
  active: boolean
  visibility: 'public' | 'draft'
  created_at: string | null
  updated_at: string | null
}

export interface FaqListResponse {
  success: boolean
  count: number
  faqs: Faq[]
}

export interface FaqTagListResponse {
  success: boolean
  count: number
  tags: FaqTag[]
}

export interface FaqDetailResponse {
  success: boolean
  faq: Faq
}

export interface FaqMutationResponse extends FaqDetailResponse {
  message: string
}

export interface TicketFaqDraftResponse extends FaqMutationResponse {
  review_required: boolean
}

export interface AssigneeListResponse {
  success: boolean
  count: number
  assignees: Relation[]
}

export interface TicketFilterOptionsResponse {
  success: boolean
  requesters: Relation[]
  teams: Relation[]
  tags: Relation[]
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

export interface TicketCategoryDetailResponse {
  success: boolean
  category: TicketCategory
}

export interface TicketCategoryMutationResponse extends TicketCategoryDetailResponse {
  message: string
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
    assigned_to_me?: number
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
