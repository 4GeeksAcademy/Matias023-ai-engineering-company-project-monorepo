import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  getInventoryProducts,
  createOutboundOrder,
  type SKUResponse,
  type ExitType,
} from '../inventory/inventoryApi'
import '../App.css'

type FieldErrors = Partial<
  Record<'sku_id' | 'quantity' | 'exit_type' | 'tracking_number', string>
>

const OUT_OF_STOCK = 0
const LOW_STOCK_MAX = 10

export default function OutboundOrderPage() {
  const location = useLocation()
  const preselected = (location.state as { preselectedProduct?: SKUResponse } | null)
    ?.preselectedProduct

  const [products, setProducts] = useState<SKUResponse[]>([])
  const [productsLoading, setProductsLoading] = useState(true)
  const [productsError, setProductsError] = useState<string | null>(null)

  const [selectedSkuId, setSelectedSkuId] = useState<number | ''>(
    preselected ? preselected.id : '',
  )
  const [quantity, setQuantity] = useState('')
  const [exitType, setExitType] = useState<ExitType | ''>('')
  const [trackingNumber, setTrackingNumber] = useState('')

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Track the refreshed product after submission so we show new stock
  const [refreshedProducts, setRefreshedProducts] = useState<SKUResponse[] | null>(null)

  const fetchProducts = useCallback(async () => {
    return getInventoryProducts()
  }, [])

  useEffect(() => {
    fetchProducts()
      .then((data) => {
        setProducts(data)
        setRefreshedProducts(null)
      })
      .catch((err: unknown) => {
        setProductsError(err instanceof Error ? err.message : 'Unknown error')
      })
      .finally(() => {
        setProductsLoading(false)
      })
  }, [fetchProducts])

  const selectedProduct = products.find((p) => p.id === selectedSkuId) ?? null
  const currentStock = selectedProduct?.current_stock ?? 0
  const qtyParsed = Number(quantity)
  const exceedsStock = Number.isFinite(qtyParsed) && qtyParsed > currentStock

  // Use refreshed product stock after successful submission
  const refreshedProduct =
    refreshedProducts?.find((p) => p.id === selectedSkuId) ?? null

  function validate(): FieldErrors {
    const errors: FieldErrors = {}

    if (selectedSkuId === '') {
      errors.sku_id = 'Select a product.'
    }

    const qty = Number(quantity)
    if (!quantity.trim() || !Number.isInteger(qty) || qty <= 0) {
      errors.quantity = 'Quantity must be a positive integer.'
    }

    if (!exitType) {
      errors.exit_type = 'Select exit type.'
    }

    if (exitType === 'dispatch' && !trackingNumber.trim()) {
      errors.tracking_number = 'Tracking number is required for dispatch.'
    }

    if (exitType === 'loss' && trackingNumber.trim()) {
      errors.tracking_number = 'Tracking number must be empty for loss.'
    }

    return errors
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return

    const errors = validate()
    setFieldErrors(errors)
    setFormError(null)
    setSuccessMessage(null)

    if (Object.keys(errors).length > 0) return

    setSubmitting(true)

    try {
      await createOutboundOrder({
        sku_id: selectedSkuId as number,
        quantity: qtyParsed,
        exit_type: exitType as ExitType,
        tracking_number: exitType === 'dispatch' ? trackingNumber.trim() : null,
        warehouse: (selectedProduct as SKUResponse).warehouse,
      })

      setSuccessMessage(
        `Outbound order registered for "${(selectedProduct as SKUResponse).name}".`,
      )
      setQuantity('')
      setExitType('')
      setTrackingNumber('')
      setFieldErrors({})

      // Refresh product list to show updated stock
      const updated = await getInventoryProducts()
      setProducts(updated)
      setRefreshedProducts(updated)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not register outbound order.')
    } finally {
      setSubmitting(false)
    }
  }

  const displayProduct = refreshedProduct ?? selectedProduct

  return (
    <main className="page">
      <section className="header">
        <div>
          <p className="eyebrow">TrackFlow Operations</p>
          <h1>Outbound order</h1>
          <p className="subtitle">
            Register a dispatch or loss from warehouse stock.
          </p>
        </div>

        <div className="header-actions">
          <Link to="/backoffice/inventory/products" className="secondary-button nav-link">
            Products
          </Link>
          <Link to="/backoffice/inventory/orders/inbound" className="secondary-button nav-link">
            Inbound
          </Link>
          <Link to="/backoffice/inventory/orders" className="secondary-button nav-link">
            Orders history
          </Link>
        </div>
      </section>

      {successMessage && (
        <div className="action-message success-message">{successMessage}</div>
      )}

      {formError && (
        <div className="action-message error-message">{formError}</div>
      )}

      {productsLoading && (
        <section className="state-card">Loading products…</section>
      )}

      {productsError && (
        <section className="state-card error">
          <p>Could not load products: {productsError}</p>
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

      {!productsLoading && !productsError && (
        <form className="create-card" onSubmit={handleSubmit} noValidate>
          <div className="form-heading">
            <h2>Dispatch details</h2>
          </div>

          <div className="form-grid">
            <label>
              Product
              <select
                value={selectedSkuId}
                onChange={(e) => {
                  setSelectedSkuId(e.target.value === '' ? '' : Number(e.target.value))
                  setRefreshedProducts(null)
                }}
              >
                <option value="">Select a product</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {fieldErrors.sku_id && (
                <span className="field-error">{fieldErrors.sku_id}</span>
              )}
            </label>

            <label>
              SKU
              <input readOnly value={displayProduct?.sku ?? ''} />
            </label>

            <label>
              Warehouse
              <input readOnly value={displayProduct?.warehouse ?? ''} />
            </label>

            {/* ── Reactive current_stock display ── */}
            <label className="notes-field">
              Current stock
              <div
                className={`stock-display ${
                  currentStock === OUT_OF_STOCK
                    ? 'stock-out'
                    : currentStock <= LOW_STOCK_MAX
                      ? 'stock-low'
                      : 'stock-healthy'
                }`}
              >
                {selectedProduct
                  ? `${currentStock} unit${currentStock === 1 ? '' : 's'} available`
                  : '—'}
              </div>
            </label>

            <label>
              Quantity
              <input
                type="number"
                min="1"
                step="1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
              {fieldErrors.quantity && (
                <span className="field-error">{fieldErrors.quantity}</span>
              )}
              {exceedsStock && !fieldErrors.quantity && (
                <span className="field-warning">
                  Warning: quantity exceeds available stock ({currentStock}).
                </span>
              )}
            </label>

            <label>
              Exit type
              <select
                value={exitType}
                onChange={(e) => setExitType(e.target.value as ExitType | '')}
              >
                <option value="">Select type</option>
                <option value="dispatch">Dispatch</option>
                <option value="loss">Loss</option>
              </select>
              {fieldErrors.exit_type && (
                <span className="field-error">{fieldErrors.exit_type}</span>
              )}
            </label>

            {exitType === 'dispatch' && (
              <label>
                Tracking number
                <input
                  type="text"
                  placeholder="e.g. 1Z999AA10123456784"
                  value={trackingNumber}
                  onChange={(e) => setTrackingNumber(e.target.value)}
                />
                {fieldErrors.tracking_number && (
                  <span className="field-error">{fieldErrors.tracking_number}</span>
                )}
              </label>
            )}

            {exitType === 'loss' && (
              <label>
                Tracking number
                <input readOnly value="Not applicable for losses" />
                {fieldErrors.tracking_number && (
                  <span className="field-error">{fieldErrors.tracking_number}</span>
                )}
              </label>
            )}
          </div>

          <button
            type="submit"
            className="primary-button"
            disabled={submitting}
            style={{ marginTop: '1rem' }}
          >
            {submitting ? 'Registering…' : 'Register outbound'}
          </button>
        </form>
      )}
    </main>
  )
}