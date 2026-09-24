import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  getInventoryProducts,
  createInboundOrder,
  type SKUResponse,
} from '../inventory/inventoryApi'
import '../App.css'

type FieldErrors = Partial<Record<'sku_id' | 'quantity' | 'reference', string>>

export default function InboundOrderPage() {
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
  const [reference, setReference] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const fetchProducts = useCallback(async () => {
    return getInventoryProducts()
  }, [])

  useEffect(() => {
    fetchProducts()
      .then((data) => {
        setProducts(data)
      })
      .catch((err: unknown) => {
        setProductsError(err instanceof Error ? err.message : 'Unknown error')
      })
      .finally(() => {
        setProductsLoading(false)
      })
  }, [fetchProducts])

  const selectedProduct = products.find((p) => p.id === selectedSkuId) ?? null

  function validate(): FieldErrors {
    const errors: FieldErrors = {}

    if (selectedSkuId === '') {
      errors.sku_id = 'Select a product.'
    }

    const qty = Number(quantity)
    if (!quantity.trim() || !Number.isInteger(qty) || qty <= 0) {
      errors.quantity = 'Quantity must be a positive integer.'
    }

    if (!reference.trim()) {
      errors.reference = 'Reference is required.'
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
      await createInboundOrder({
        sku_id: selectedSkuId as number,
        quantity: Number(quantity),
        reference: reference.trim(),
        warehouse: (selectedProduct as SKUResponse).warehouse,
      })

      setSuccessMessage(
        `Inbound order registered for "${(selectedProduct as SKUResponse).name}".`,
      )
      setQuantity('')
      setReference('')
      setSelectedSkuId('')
      setFieldErrors({})
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not register inbound order.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="page">
      <section className="header">
        <div>
          <p className="eyebrow">TrackFlow Operations</p>
          <h1>Inbound order</h1>
          <p className="subtitle">
            Register a goods receipt from a client brand.
          </p>
        </div>

        <div className="header-actions">
          <Link to="/backoffice/inventory/products" className="secondary-button nav-link">
            Products
          </Link>
          <Link to="/backoffice/inventory/orders/outbound" className="secondary-button nav-link">
            Outbound
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
            <h2>Receipt details</h2>
          </div>

          <div className="form-grid">
            <label>
              Product
              <select
                value={selectedSkuId}
                onChange={(e) => setSelectedSkuId(e.target.value === '' ? '' : Number(e.target.value))}
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
              <input readOnly value={selectedProduct?.sku ?? ''} />
            </label>

            <label>
              Warehouse
              <input readOnly value={selectedProduct?.warehouse ?? ''} />
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
            </label>

            <label>
              Reference
              <input
                type="text"
                placeholder="e.g. PO-2024-0098"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
              {fieldErrors.reference && (
                <span className="field-error">{fieldErrors.reference}</span>
              )}
            </label>
          </div>

          <button
            type="submit"
            className="primary-button"
            disabled={submitting}
            style={{ marginTop: '1rem' }}
          >
            {submitting ? 'Registering…' : 'Register inbound'}
          </button>
        </form>
      )}
    </main>
  )
}