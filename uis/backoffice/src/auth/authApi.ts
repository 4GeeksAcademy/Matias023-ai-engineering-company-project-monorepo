/**
 * API functions for authentication and user profile endpoints.
 */

import { trackValidationError, trackServerError } from '../services/apiTelemetry'

function safeDetail(data: unknown, fallback: string): string {
  if (
    data &&
    typeof data === 'object' &&
    typeof (data as Record<string, unknown>).detail === 'string' &&
    (data as Record<string, unknown>).detail !== ''
  ) {
    return (data as Record<string, unknown>).detail as string
  }
  return fallback
}

export type LoginPayload = {
  email: string
  password: string
}

export type TokenResponse = {
  access_token: string
  token_type: string
}

export type RegisterPayload = {
  email: string
  password: string
  name?: string
  phone?: string
  address?: string
}

export type UserResponse = {
  id: number
  email: string
  is_active: boolean
  role: 'admin' | 'manager' | 'user'
  created_at: string
  uuid: string | null
}

export type ProfileResponse = {
  id: number
  user_id: number
  name: string | null
  phone: string | null
  address: string | null
}

export type ProfileUpdatePayload = {
  name?: string
  phone?: string
  address?: string
}

export type UserWithProfileResponse = UserResponse & {
  profile: ProfileResponse | null
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    // ── Telemetry: frontend-observed API errors ──
    if (response.status === 422) {
      trackValidationError('/api/auth/login', 'POST', 422)
    } else if (response.status >= 500) {
      trackServerError('/api/auth/login', 'POST', response.status)
    }

    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to sign in. Please check your credentials and try again.'))
  }

  return response.json()
}

export async function register(payload: RegisterPayload): Promise<UserResponse> {
  const response = await fetch('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    // ── Telemetry: frontend-observed API errors ──
    if (response.status === 422) {
      trackValidationError('/api/users', 'POST', 422)
    } else if (response.status >= 500) {
      trackServerError('/api/users', 'POST', response.status)
    }

    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to create the account. Please try again.'))
  }

  return response.json()
}

export async function getMe(token: string): Promise<UserWithProfileResponse> {
  const response = await fetch('/api/auth/me', {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    // ── Telemetry: frontend-observed API errors ──
    if (response.status === 422) {
      trackValidationError('/api/auth/me', 'GET', 422)
    } else if (response.status >= 500) {
      trackServerError('/api/auth/me', 'GET', response.status)
    }

    throw new Error('Session expired')
  }

  return response.json()
}

export async function getProfile(token: string): Promise<ProfileResponse> {
  const response = await fetch('/api/profiles/me', {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to load profile. Please try again.'))
  }

  return response.json()
}

export async function updateProfile(
  token: string,
  payload: ProfileUpdatePayload,
): Promise<ProfileResponse> {
  const response = await fetch('/api/profiles/me', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to update profile. Please try again.'))
  }

  return response.json()
}

export async function forgotPassword(email: string): Promise<{ detail: string }> {
  const response = await fetch('/api/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to complete the request. Please try again.'))
  }

  return response.json()
}

export async function resetPassword(token: string, newPassword: string): Promise<{ detail: string }> {
  const response = await fetch('/api/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to complete the request. Please try again.'))
  }

  return response.json()
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<{ detail: string }> {
  const response = await fetch('/api/auth/change-password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(safeDetail(data, 'Unable to complete the request. Please try again.'))
  }

  return response.json()
}