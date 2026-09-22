/**
 * Unit tests for `src/auth/authApi.ts`.
 *
 * We exercise the public auth API functions by mocking `global.fetch`,
 * testing both happy paths and error fallbacks (including safeDetail
 * behavior indirectly through the public functions).
 */

/// <reference types="jest" />
/// <reference lib="dom" />

import {
  login,
  register,
  getMe,
  getProfile,
  updateProfile,
  forgotPassword,
  changePassword,
  resetPassword,
  type LoginPayload,
  type TokenResponse,
  type RegisterPayload,
  type UserResponse,
  type UserWithProfileResponse,
  type ProfileResponse,
  type ProfileUpdatePayload,
} from './authApi'

const LOGIN_FALLBACK =
  'Unable to sign in. Please check your credentials and try again.'
const GENERIC_FALLBACK = 'Unable to complete the request. Please try again.'

/**
 * Build a minimal mock Response — typed inline to avoid depending
 * on DOM types (ts-jest inline tsconfig uses lib: ["ES2023"]).
 */
function mockResponse(ok: boolean, body: unknown): { ok: boolean; json: () => Promise<unknown> } {
  return { ok, json: async () => body }
}

let fetchMock: jest.Mock

beforeEach(() => {
  fetchMock = jest.fn()
  // Assign without hard-coding DOM globals (no DOM lib in this Jest tsconfig).
  const globalObj = globalThis as unknown as { fetch: unknown }
  globalObj.fetch = fetchMock
})

afterEach(() => {
  jest.restoreAllMocks()
})

// ══════════════════════════════════════════════
// login()
// ══════════════════════════════════════════════

describe('login()', () => {
  const payload: LoginPayload = {
    email: 'test@example.com',
    password: 'strongpass123',
  }

  test('happy path: returns TokenResponse when fetch responds ok', async () => {
    const tokenResponse: TokenResponse = {
      access_token: 'jwt-token-abc',
      token_type: 'bearer',
    }
    fetchMock.mockResolvedValue(mockResponse(true, tokenResponse))

    const result = await login(payload)

    expect(result).toEqual(tokenResponse)
    // Verify it posted to the login endpoint with a JSON body
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )
  })

  test('error: uses detail message when detail is a non-empty string', async () => {
    fetchMock.mockResolvedValue(
      mockResponse(false, { detail: 'Invalid email or password' }),
    )

    await expect(login(payload)).rejects.toThrow('Invalid email or password')
  })

  test('error: falls back when detail is missing', async () => {
    fetchMock.mockResolvedValue(
      mockResponse(false, { foo: 'bar' }),
    )

    await expect(login(payload)).rejects.toThrow(LOGIN_FALLBACK)
  })

  test('error: falls back when detail is an empty string', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, { detail: '' }))

    await expect(login(payload)).rejects.toThrow(LOGIN_FALLBACK)
  })

  test('error: falls back when detail is not a string (number)', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, { detail: 500 }))

    await expect(login(payload)).rejects.toThrow(LOGIN_FALLBACK)
  })

  test('error: falls back when detail is not a string (object)', async () => {
    fetchMock.mockResolvedValue(
      mockResponse(false, { detail: { code: 'ERR' } }),
    )

    await expect(login(payload)).rejects.toThrow(LOGIN_FALLBACK)
  })
})

// ══════════════════════════════════════════════
// forgotPassword()
// ══════════════════════════════════════════════

describe('forgotPassword()', () => {
  test('happy path: returns the expected detail object', async () => {
    const body = {
      detail:
        'If an account with that email exists, a password reset link has been sent.',
    }
    fetchMock.mockResolvedValue(mockResponse(true, body))

    const result = await forgotPassword('test@example.com')

    expect(result).toEqual(body)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/forgot-password',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(forgotPassword('test@example.com')).rejects.toThrow(
      GENERIC_FALLBACK,
    )
  })
})

// ══════════════════════════════════════════════
// changePassword()
// ══════════════════════════════════════════════

describe('changePassword()', () => {
  test('happy path: returns the expected detail object', async () => {
    const body = { detail: 'Password changed successfully.' }
    fetchMock.mockResolvedValue(mockResponse(true, body))

    const result = await changePassword(
      'jwt-token-abc',
      'oldpass123',
      'newpass456',
    )

    expect(result).toEqual(body)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/change-password',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(
      changePassword('jwt-token-abc', 'oldpass123', 'newpass456'),
    ).rejects.toThrow(GENERIC_FALLBACK)
  })
})

// ══════════════════════════════════════════════
// register()
// ══════════════════════════════════════════════

describe('register()', () => {
  const payload: RegisterPayload = {
    email: 'new@example.com',
    password: 'strongpass123',
    name: 'New User',
  }

  test('happy path: returns UserResponse when fetch responds ok', async () => {
    const userResponse: UserResponse = {
      id: 1,
      email: 'new@example.com',
      is_active: true,
      role: 'user',
      created_at: '2026-01-01T00:00:00Z',
    }
    fetchMock.mockResolvedValue(mockResponse(true, userResponse))

    const result = await register(payload)

    expect(result).toEqual(userResponse)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/users',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(register(payload)).rejects.toThrow(
      'Unable to create the account. Please try again.',
    )
  })
})

// ══════════════════════════════════════════════
// getMe()
// ══════════════════════════════════════════════

describe('getMe()', () => {
  test('happy path: returns UserWithProfileResponse when fetch responds ok', async () => {
    const userWithProfile: UserWithProfileResponse = {
      id: 1,
      email: 'test@example.com',
      is_active: true,
      role: 'admin',
      created_at: '2026-01-01T00:00:00Z',
      profile: {
        id: 1,
        user_id: 1,
        name: 'Test User',
        phone: null,
        address: null,
      },
    }
    fetchMock.mockResolvedValue(mockResponse(true, userWithProfile))

    const result = await getMe('jwt-token-abc')

    expect(result).toEqual(userWithProfile)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token-abc',
        }),
      }),
    )
  })

  test('error: throws "Session expired" when fetch responds not ok', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(getMe('jwt-token-abc')).rejects.toThrow('Session expired')
  })
})

// ══════════════════════════════════════════════
// getProfile()
// ══════════════════════════════════════════════

describe('getProfile()', () => {
  test('happy path: returns ProfileResponse when fetch responds ok', async () => {
    const profile: ProfileResponse = {
      id: 1,
      user_id: 1,
      name: 'Test User',
      phone: '+1234567890',
      address: '123 Main St',
    }
    fetchMock.mockResolvedValue(mockResponse(true, profile))

    const result = await getProfile('jwt-token-abc')

    expect(result).toEqual(profile)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/profiles/me',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token-abc',
        }),
      }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(getProfile('jwt-token-abc')).rejects.toThrow(
      'Unable to load profile. Please try again.',
    )
  })
})

// ══════════════════════════════════════════════
// updateProfile()
// ══════════════════════════════════════════════

describe('updateProfile()', () => {
  const payload: ProfileUpdatePayload = {
    name: 'Updated Name',
    phone: '+9876543210',
  }

  test('happy path: returns updated ProfileResponse when fetch responds ok', async () => {
    const updatedProfile: ProfileResponse = {
      id: 1,
      user_id: 1,
      name: 'Updated Name',
      phone: '+9876543210',
      address: null,
    }
    fetchMock.mockResolvedValue(mockResponse(true, updatedProfile))

    const result = await updateProfile('jwt-token-abc', payload)

    expect(result).toEqual(updatedProfile)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/profiles/me',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token-abc',
        }),
        body: JSON.stringify(payload),
      }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(
      updateProfile('jwt-token-abc', payload),
    ).rejects.toThrow('Unable to update profile. Please try again.')
  })
})

// ══════════════════════════════════════════════
// resetPassword()
// ══════════════════════════════════════════════

describe('resetPassword()', () => {
  test('happy path: returns the expected detail object', async () => {
    const body = { detail: 'Password has been reset successfully.' }
    fetchMock.mockResolvedValue(mockResponse(true, body))

    const result = await resetPassword('reset-token-xyz', 'newpass456')

    expect(result).toEqual(body)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/reset-password',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          token: 'reset-token-xyz',
          new_password: 'newpass456',
        }),
      }),
    )
  })

  test('error: uses generic fallback when there is no valid detail', async () => {
    fetchMock.mockResolvedValue(mockResponse(false, {}))

    await expect(
      resetPassword('reset-token-xyz', 'newpass456'),
    ).rejects.toThrow(GENERIC_FALLBACK)
  })
})