// API v1 types (mirror of schema/api.v1.json). Units: mm, deg, kg, N·m.
export const CLIENT_API_VERSION = '1.0'

export type Pose6 = [number, number, number, number, number, number]

export interface HelloResult {
  api_version: string
  core_version: string
  ufactory_genesis_version: string
  ufactory_genesis_commit: string
  pinocchio_version: string
  capabilities: string[]
  backend: { kin: string; dyn: string }
}

export interface RobotListItem {
  key: string
  robot_name: string
  dof: number
  end_effectors: string[]
}

export interface RobotInfo {
  key: string
  robot_name: string
  dof: number
  joint_names: string[]
  effort_limits_nm: number[]
  visual_urdf_relpath: string
  home_q_deg: number[]
  end_effectors: string[]
  end_effector: string
  /** Default TCP offset of the end effector [x,y,z mm, r,p,y deg]; visual only, adds no mass. */
  default_tcp_offset: number[]
  default_tcp_source: string
}

export interface RobotLoadResult extends RobotInfo {
  session_id: string
  limits_deg: [number, number][]
  default_q_deg: number[]
}

export interface FkResult {
  tcp_pose: Pose6
  flange_pose: Pose6
}

export interface TorqueResult {
  tau_nm: number[]
  tau_arm_nm?: number[]
  tau_payload_nm?: number[]
  effort_limits_nm: number[]
  utilization: number[]
  over_limit: boolean[]
}

export interface IkSolution {
  q_deg: number[]
  err_mm: number
  err_deg: number
  branch: { elbow: 'up' | 'down'; wrist: 'flip' | 'noflip' }
  limit_margin_deg: number
}

export interface CheckSolution extends IkSolution, TorqueResult {
  flange_pose: Pose6
}

export interface CheckResult {
  solutions: CheckSolution[]
  recommended: number
  reachable: boolean
}

export interface RpcErrorObject {
  code: number
  message: string
  data?: unknown
}

export interface JogResult {
  q_deg: number[]
  tcp_pose: Pose6
}

export interface ConnectionStatus { mode: string; ip: string; connected: boolean; last_error: string }
export interface ScriptStatus { job_id: string; status: string; output: string; error: string; elapsed_s: number }
