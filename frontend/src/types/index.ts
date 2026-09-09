// Bridge 前端类型定义

/** 沟通模式 */
export type Mode = 'standard' | 'hearing' | 'elderly' | 'visual'

/** 业务场景 */
export type Scene = 'hospital' | 'government'

/** 说话人角色 */
export type Role = 'staff' | 'user' | 'assistant' | 'system'

/** 流式事件类型，对齐后端 EventType */
export type EventType =
  | 'transcript.partial'
  | 'transcript.final'
  | 'agent.started'
  | 'agent.thinking'
  | 'agent.completed'
  | 'tool.started'
  | 'tool.completed'
  | 'tool.failed'
  | 'message.delta'
  | 'message.completed'
  | 'digital_human.speak'
  | 'digital_human.audio_ready'
  | 'widget.show'
  | 'widget.update'
  | 'widget.close'
  | 'error'

/** Widget 类型 */
export type WidgetType =
  'map_route' | 'location' | 'knowledge_source' | 'task_result' | 'translation'

/** 统一事件载荷 */
export interface BridgeEvent {
  type: EventType
  session_id: string
  seq: number
  data: Record<string, unknown>
}

/** 会话 */
export interface Session {
  session_id: string
  scene: Scene
  mode: Mode
  status: 'active' | 'closed'
}

/** 消息 */
export interface Message {
  id: string
  session_id: string
  role: Role
  content: string
  speaker?: string
  language?: string
  message_type?: 'text' | 'audio' | 'transcript'
  created_at?: string
  run_id?: string
  send_status?: 'pending' | 'sent' | 'failed'
}

/** Agent 执行状态 */
export type AgentStatus = 'idle' | 'thinking' | 'running' | 'completed' | 'failed'

/** Widget 数据 */
export interface WidgetData {
  widget_id: string
  widget_type: WidgetType
  payload: Record<string, unknown>
}
