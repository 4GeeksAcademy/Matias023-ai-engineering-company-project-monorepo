import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './pages/ProtectedRoute'
import './App.css'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const ChangePasswordPage = lazy(() => import('./pages/ChangePasswordPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const SuppliersPage = lazy(() => import('./pages/SuppliersPage'))
const InventoryProductsPage = lazy(() => import('./pages/InventoryProductsPage'))
const InboundOrderPage = lazy(() => import('./pages/InboundOrderPage'))
const OutboundOrderPage = lazy(() => import('./pages/OutboundOrderPage'))
const OrdersListPage = lazy(() => import('./pages/OrdersListPage'))
const IncidentsListPage = lazy(() => import('./pages/IncidentsListPage'))
const IncidentFormPage = lazy(() => import('./pages/IncidentFormPage'))
const IncidentsSummaryPage = lazy(() => import('./pages/IncidentsSummaryPage'))

export default function App() {
  return (
    <Suspense
      fallback={
        <main className="page">
          <section className="state-card" role="status">
            Loading page...
          </section>
        </main>
      }
    >
      <Routes>
        {/* Public routes — no auth required */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

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
              <InventoryProductsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders/inbound"
          element={
            <ProtectedRoute>
              <InboundOrderPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders/outbound"
          element={
            <ProtectedRoute>
              <OutboundOrderPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backoffice/inventory/orders"
          element={
            <ProtectedRoute>
              <OrdersListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents"
          element={
            <ProtectedRoute>
              <IncidentsListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents/new"
          element={
            <ProtectedRoute>
              <IncidentFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/incidents/summary"
          element={
            <ProtectedRoute>
              <IncidentsSummaryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
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
