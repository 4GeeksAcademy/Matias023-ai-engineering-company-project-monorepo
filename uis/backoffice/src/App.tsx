import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'

// ──────────────────────────────────────────────
// Eager imports — critical path pages that appear
// on first render (login, register, default
// redirect after auth).
// ──────────────────────────────────────────────

import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import SuppliersPage from './pages/SuppliersPage'
import ProtectedRoute from './pages/ProtectedRoute'
import LoadingFallback from './LoadingFallback'

// ──────────────────────────────────────────────
// Lazy imports — every other page is loaded
// on-demand when its route is first navigated to.
// React.lazy() defers the module import until
// the component is actually rendered.
// ──────────────────────────────────────────────

const LazyForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'))
const LazyResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const LazyChangePasswordPage = lazy(() => import('./pages/ChangePasswordPage'))
const LazyProfilePage = lazy(() => import('./pages/ProfilePage'))
const LazyInventoryProductsPage = lazy(() => import('./pages/InventoryProductsPage'))
const LazyInboundOrderPage = lazy(() => import('./pages/InboundOrderPage'))
const LazyOutboundOrderPage = lazy(() => import('./pages/OutboundOrderPage'))
const LazyOrdersListPage = lazy(() => import('./pages/OrdersListPage'))
const LazyIncidentsListPage = lazy(() => import('./pages/IncidentsListPage'))
const LazyIncidentFormPage = lazy(() => import('./pages/IncidentFormPage'))
const LazyIncidentsSummaryPage = lazy(() => import('./pages/IncidentsSummaryPage'))

// ──────────────────────────────────────────────
// App — route definitions
// ──────────────────────────────────────────────

export default function App() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* Public routes — no auth required */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<LazyForgotPasswordPage />} />
        <Route path="/reset-password" element={<LazyResetPasswordPage />} />

        {/* Protected routes — require auth */}
        <Route
          path="/suppliers"
          element={
            <ProtectedRoute>
              <SuppliersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/products"
          element={
            <ProtectedRoute>
              <LazyInventoryProductsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders/inbound"
          element={
            <ProtectedRoute>
              <LazyInboundOrderPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders/outbound"
          element={
            <ProtectedRoute>
              <LazyOutboundOrderPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders"
          element={
            <ProtectedRoute>
              <LazyOrdersListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents"
          element={
            <ProtectedRoute>
              <LazyIncidentsListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents/new"
          element={
            <ProtectedRoute>
              <LazyIncidentFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents/summary"
          element={
            <ProtectedRoute>
              <LazyIncidentsSummaryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/profile"
          element={
            <ProtectedRoute>
              <LazyProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/change-password"
          element={
            <ProtectedRoute>
              <LazyChangePasswordPage />
            </ProtectedRoute>
          }
        />

        {/* Compatibility redirect from old /profile to /account/profile */}
        <Route
          path="/profile"
          element={<Navigate to="/account/profile" replace />}
        />

        {/* Default redirect */}
        <Route path="*" element={<Navigate to="/suppliers" replace />} />
      </Routes>
    </Suspense>
  )
}
