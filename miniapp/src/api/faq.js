import { adminRequest } from './admin.js'
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

export async function fetchFaq() {
  const response = await fetch('/api/faq')
  return parseJsonResponse(response)
}

export function fetchAdminFaq({ initData = '' } = {}) {
  return adminRequest('/api/admin/faq', { initData })
}

export function saveAdminFaq({
  initData = '',
  id = 0,
  question = '',
  answer = '',
  linkUrl = '',
  buttonLabel = '',
} = {}) {
  return adminRequest('/api/admin/faq/save', {
    initData,
    body: {
      id,
      question,
      answer,
      link_url: linkUrl,
      button_label: buttonLabel,
    },
  })
}

export function deleteAdminFaq({ initData = '', id = 0 } = {}) {
  return adminRequest('/api/admin/faq/delete', {
    initData,
    body: { id },
  })
}
