import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  getInventoryProducts,
  type SKUResponse,
} from '../inventory/inventoryApi'
import '../App.css'

// ──────────────────────────────────────────────
// Stock-level helpers
// ──────────────────────────────────────────────

const OUT_OF_STOCK = 0
const LOW_STOCK_MAX = 10

type StockLevel = 'healthy' | 'low' | 'out'

function getStockLevel(currentStock: number): StockLevel {
  if (currentStock === OUT_OF_STOCK) return 'out'
  if (currentStock <= LOW_STOCK_MAX) return 'low'
  return 'healthy'
}

const STOCK_LABEL: Record<StockLevel, string> = {
  healthy: 'In stock',
  low: 'Low stock',
  out: 'Out of stock',
}

const STOCK_CLASS: Record<StockLevel, string> = {
  healthy: 'stock-healthy',
  low: 'stock-low',
  out: 'stock-out',
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function formatCategory(cat: string): string {
  return cat.charAt(0).toUpperCase() + cat.slice(1)
}

// ──────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────

export default function InventoryProductsPage() {
  const navigate = useNavigate()
  const [products, setProducts] = useState<SKUResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProducts = useCallback(async () => {
    return getInventoryProducts()
  }, [])

  useEffect(() => {
    fetchProducts()
      .then((data) => {
        setProducts(data)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Unknown API error')
      })
      .finally(() => {
        setLoading(false)
      })
  }, [fetchProducts])

  function handleInbound(product: SKUResponse) {
    navigate('/backoffice/inventory/orders/inbound', {
      state: { preselectedProduct: product },
    })
  }

  function handleOutbound(product: SKUResponse) {
    navigate('/backoffice/inventory/orders/outbound', {
      state: { preselectedProduct: product },
    })
  }

  return (
    <main className="page">
      <section className="header">
        <div>
          <p className="eyebrow">TrackFlow Operations</p>
          <h1>Inventory</h1>
          <p className="subtitle">
            Products and stock levels across LA and ZGZ warehouses.
          </p>
        </div>

        <div className="header-actions">
          <Link to="/backoffice/inventory/orders" className="secondary-button nav-link">
            Orders history
          </Link>
          <Link to="/suppliers" className="secondary-button nav-link">
            Suppliers
          </Link>

          <div className="supplier-count">
            <strong>{products.length}</strong>
            <span>products</span>
          </div>
        </div>
      </section>

      {loading && (
        <section className="state-card">Loading products…</section>
      )}

      {!loading && error && (
        <section className="state-card error">
          <p>Could not load products: {error}</p>
          <button
            type="button"
            className="secondary-button"
            style={{ marginTop: '0.75rem' }}
            onClick={() => void fetchProducts()}
          >
            Retry
          </button>
        </section>
      )}

      {!loading && !error && products.length === 0 && (
        <section className="state-card">
          No products found.
        </section>
      )}

      {!loading && !error && products.length > 0 && (
        <section className="table-card">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>SKU</th>
                  <th>Client</th>
                  <th>Category</th>
                  <th>Warehouse</th>
                  <th>Stock</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {products.map((product) => {
                  const level = getStockLevel(product.current_stock)

                  return (
                    <tr key={product.id}>
                      <td>
                        <strong>{product.name}</strong>
                      </td>
                      <td>
                        <span className="secondary-text" style={{ margin: 0 }}>
                          {product.sku}
                        </span>
                      </td>
                      <td>{product.client_name}</td>
                      <td>{formatCategory(product.category)}</td>
                      <td>{product.warehouse}</td>
                      <td>
                        <span className={`status ${STOCK_CLASS[level]}`}>
                          {product.current_stock} — {STOCK_LABEL[level]}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            type="button"
                            className="small-button"
                            onClick={() => handleInbound(product)}
                          >
                            Inbound
                          </button>
                          <button
                            type="button"
                            className="small-button"
                            onClick={() => handleOutbound(product)}
                          >
                            Outbound
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  )
}