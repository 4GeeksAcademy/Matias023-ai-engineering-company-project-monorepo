import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getInventoryOrders,
  type StockMovementResponse,
} from '../inventory/inventoryApi'
import '../App.css'

function isEntry(movement: StockMovementResponse): boolean {
  return movement.kind === 'entry'
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

export default function OrdersListPage() {
  const [movements, setMovements] = useState<StockMovementResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchOrders = useCallback(async () => {
    return getInventoryOrders()
  }, [])

  useEffect(() => {
    fetchOrders()
      .then((data) => {
        setMovements(data)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Unknown API error')
      })
      .finally(() => {
        setLoading(false)
      })
  }, [fetchOrders])

  return (
    <main className="page">
      <section className="header">
        <div>
          <p className="eyebrow">TrackFlow Operations</p>
          <h1>Orders history</h1>
          <p className="subtitle">
            All stock movements — inbound receipts and outbound dispatches/losses.
          </p>
        </div>

        <div className="header-actions">
          <Link to="/backoffice/inventory/products" className="secondary-button nav-link">
            Products
          </Link>
          <Link to="/backoffice/inventory/orders/inbound" className="secondary-button nav-link">
            Inbound
          </Link>
          <Link to="/backoffice/inventory/orders/outbound" className="secondary-button nav-link">
            Outbound
          </Link>

          <div className="supplier-count">
            <strong>{movements.length}</strong>
            <span>movements</span>
          </div>
        </div>
      </section>

      {loading && (
        <section className="state-card">Loading orders…</section>
      )}

      {!loading && error && (
        <section className="state-card error">
          <p>Could not load orders: {error}</p>
          <button
            type="button"
            className="secondary-button"
            style={{ marginTop: '0.75rem' }}
            onClick={() => void fetchOrders()}
          >
            Retry
          </button>
        </section>
      )}

      {!loading && !error && movements.length === 0 && (
        <section className="state-card">
          No stock movements found.
        </section>
      )}

      {!loading && !error && movements.length > 0 && (
        <section className="table-card">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>SKU</th>
                  <th>Type</th>
                  <th>Quantity</th>
                  <th>Warehouse</th>
                  <th>Reference / Exit</th>
                  <th>Tracking</th>
                  <th>User</th>
                  <th>Date</th>
                </tr>
              </thead>

              <tbody>
                {movements.map((m) => (
                  <tr key={`${m.kind}-${m.id}`} className={isEntry(m) ? 'row-entry' : 'row-exit'}>
                    <td>
                      <strong>{m.sku_name}</strong>
                    </td>
                    <td>
                      <span className="secondary-text" style={{ margin: 0 }}>
                        {m.sku}
                      </span>
                    </td>
                    <td>
                      <span className={`status ${isEntry(m) ? 'status-entry' : 'status-exit'}`}>
                        {isEntry(m) ? 'Inbound' : 'Outbound'}
                      </span>
                    </td>
                    <td>{m.quantity}</td>
                    <td>{m.warehouse}</td>
                    <td>
                      {m.reference ?? (m.exit_type ? m.exit_type.charAt(0).toUpperCase() + m.exit_type.slice(1) : '—')}
                    </td>
                    <td>{m.tracking_number ?? '—'}</td>
                    <td className="uuid-cell" title={m.user_uuid}>
                      {m.user_uuid}
                    </td>
                    <td>{formatDateTime(m.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  )
}