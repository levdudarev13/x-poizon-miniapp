import { repairMojibakeDeep } from '../utils/text.js'

const DELIVERY_FIELDS = [
  'recipient_name',
  'phone',
  'city',
  'street',
  'house',
  'apartment',
  'comment',
]

function createEmptyDeliveryData() {
  return DELIVERY_FIELDS.reduce((accumulator, field) => ({
    ...accumulator,
    [field]: '',
  }), {})
}

function normalizeDeliveryData(deliveryData = {}) {
  return DELIVERY_FIELDS.reduce((accumulator, field) => ({
    ...accumulator,
    [field]: String(deliveryData?.[field] || ''),
  }), createEmptyDeliveryData())
}

async function parseJsonResponse(response) {
  let data = {}

  try {
    data = repairMojibakeDeep(await response.json())
  } catch {
    data = {}
  }

  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`)
  }

  if (data?.error) {
    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return data
}

function normalizeDeliveryResponse(payload = {}) {
  return {
    delivery_data: normalizeDeliveryData(payload?.delivery_data),
    is_complete: Boolean(payload?.is_complete),
    updated_at: String(payload?.updated_at || ''),
  }
}

export async function fetchDeliveryProfile({ userId } = {}) {
  if (!userId) {
    throw new Error('Missing userId')
  }

  const response = await fetch(`/api/profile/delivery?user_id=${userId}`, {
    headers: {
      'Content-Type': 'application/json',
    },
  })

  const data = await parseJsonResponse(response)
  return normalizeDeliveryResponse(data)
}

export async function saveDeliveryProfile({ userId, deliveryData } = {}) {
  if (!userId) {
    throw new Error('Missing userId')
  }

  const response = await fetch('/api/profile/delivery/save', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
      delivery_data: normalizeDeliveryData(deliveryData),
    }),
  })

  const data = await parseJsonResponse(response)
  return normalizeDeliveryResponse(data)
}
