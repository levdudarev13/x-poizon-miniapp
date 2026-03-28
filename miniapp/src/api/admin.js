import { repairMojibakeDeep } from '../utils/text.js'

async function parseJsonResponse(response) {
  let data = {}

  try {
    data = repairMojibakeDeep(await response.json())
  } catch {
    data = {}
  }

  if (!response.ok) {
    const error = new Error(data.error || `HTTP ${response.status}`)
    if (data && typeof data === 'object') {
      Object.assign(error, data)
    }
    throw error
  }

  if (data?.error) {
    const error = new Error(data.error || `HTTP ${response.status}`)
    if (data && typeof data === 'object') {
      Object.assign(error, data)
    }
    throw error
  }

  return data
}

export async function bootstrapWithInitData({ userId = 0, initData = '' } = {}) {
  const response = await fetch('/api/bootstrap', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
      init_data: initData,
    }),
  })

  return parseJsonResponse(response)
}

export async function adminRequest(path, { initData = '', method = 'POST', body = {} } = {}) {
  if (!initData) {
    throw new Error('Missing initData')
  }

  const response = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      init_data: initData,
      ...body,
    }),
  })

  return parseJsonResponse(response)
}

export function fetchAdminSettings({ initData = '' } = {}) {
  return adminRequest('/api/admin/settings', { initData })
}

export function updateAdminSetting({ initData = '', field = '', value = '' } = {}) {
  return adminRequest('/api/admin/settings/update', {
    initData,
    body: { field, value },
  })
}

export function resetAdminSettings({ initData = '' } = {}) {
  return adminRequest('/api/admin/settings/reset', { initData })
}

export function fetchAdminShowcase({ initData = '' } = {}) {
  return adminRequest('/api/admin/showcase', { initData })
}

export function updateAdminShowcase({ initData = '', links = [] } = {}) {
  return adminRequest('/api/admin/showcase/update', {
    initData,
    body: { links },
  })
}

export function fetchAdminMessages({ initData = '', page = 1, pageSize = 10 } = {}) {
  return adminRequest('/api/admin/messages', {
    initData,
    body: { page, page_size: pageSize },
  })
}

export function clearAdminMessages({ initData = '' } = {}) {
  return adminRequest('/api/admin/messages/clear', { initData })
}

export function fetchAdminOrders({ initData = '' } = {}) {
  return adminRequest('/api/admin/orders', { initData })
}

export function updateAdminOrder({
  initData = '',
  action = '',
  userId = 0,
  calcId = 0,
  trackingNumber = '',
  itemNumber = '',
} = {}) {
  return adminRequest('/api/admin/orders/update', {
    initData,
    body: {
      action,
      user_id: userId,
      calc_id: calcId,
      tracking_number: trackingNumber,
      item_number: itemNumber,
    },
  })
}

export function fetchAdminCarts({ initData = '' } = {}) {
  return adminRequest('/api/admin/carts', { initData })
}

export async function fetchViewerAvatar({ initData = '' } = {}) {
  if (!initData) {
    throw new Error('Missing initData')
  }

  const response = await fetch('/api/avatar', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      init_data: initData,
    }),
  })

  if (!response.ok) {
    let data = {}

    try {
      data = await response.json()
    } catch {
      data = {}
    }

    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return response.blob()
}

export async function fetchAdminAvatar({ initData = '', userId = 0 } = {}) {
  if (!initData) {
    throw new Error('Missing initData')
  }

  if (!userId) {
    throw new Error('Missing userId')
  }

  const response = await fetch('/api/admin/avatar', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      init_data: initData,
      user_id: userId,
    }),
  })

  if (!response.ok) {
    let data = {}

    try {
      data = await response.json()
    } catch {
      data = {}
    }

    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return response.blob()
}
