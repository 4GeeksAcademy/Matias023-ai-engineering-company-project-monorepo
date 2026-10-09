import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './pages/ProtectedRoute'
import PageTracked from './pages/PageTracked'
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
        <Route
          path="/login"
          element={<PageTracked><LoginPage /></PageTracked>}
        />
        <Route
          path="/register"
          element={<PageTracked><RegisterPage /></PageTracked>}
        />
        <Route
          path="/forgot-password"
          element={<PageTracked><ForgotPasswordPage /></PageTracked>}
        />
        <Route
          path="/reset-password"
          element={<PageTracked><ResetPasswordPage /></PageTracked>}
        />

        {/* Protected routes — require auth */}
        <Route
          path="/suppliers"
          element={
            <PageTracked>
              <ProtectedRoute>
                <SuppliersPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/backoffice/inventory/products"
          element={
            <PageTracked>
              <ProtectedRoute>
                <InventoryProductsPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/backoffice/inventory/orders/inbound"
          element={
            <PageTracked>
              <ProtectedRoute>
                <InboundOrderPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/backoffice/inventory/orders/outbound"
          element={
            <PageTracked>
              <ProtectedRoute>
                <OutboundOrderPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/backoffice/inventory/orders"
          element={
            <PageTracked>
              <ProtectedRoute>
                <OrdersListPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/incidents"
          element={
            <PageTracked>
              <ProtectedRoute>
                <IncidentsListPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/incidents/new"
          element={
            <PageTracked>
              <ProtectedRoute>
                <IncidentFormPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/incidents/summary"
          element={
            <PageTracked>
              <ProtectedRoute>
                <IncidentsSummaryPage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/account/profile"
          element={
            <PageTracked>
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            </PageTracked>
          }
        />
        <Route
          path="/account/change-password"
          element={
            <PageTracked>
              <ProtectedRoute>
                <ChangePasswordPage />
              </ProtectedRoute>
            </PageTracked>
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
