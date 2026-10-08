import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import ChangePasswordPage from './pages/ChangePasswordPage'
import ProfilePage from './pages/ProfilePage'
import SuppliersPage from './pages/SuppliersPage'
import InventoryProductsPage from './pages/InventoryProductsPage'
import InboundOrderPage from './pages/InboundOrderPage'
import OutboundOrderPage from './pages/OutboundOrderPage'
import OrdersListPage from './pages/OrdersListPage'
import IncidentsListPage from './pages/IncidentsListPage'
import IncidentFormPage from './pages/IncidentFormPage'
import IncidentsSummaryPage from './pages/IncidentsSummaryPage'
import ProtectedRoute from './pages/ProtectedRoute'
import PageTracked from './pages/PageTracked'

export default function App() {
  return (
    <Routes>
      {/* Public routes — no auth required */}
      <Route path="/login" element={<PageTracked><LoginPage /></PageTracked>} />
      <Route path="/register" element={<PageTracked><RegisterPage /></PageTracked>} />
      <Route path="/forgot-password" element={<PageTracked><ForgotPasswordPage /></PageTracked>} />
      <Route path="/reset-password" element={<PageTracked><ResetPasswordPage /></PageTracked>} />

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
  )
}
