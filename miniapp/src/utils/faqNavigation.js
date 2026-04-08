export const OPEN_FAQ_REQUEST_EVENT = 'x-poizon:open-faq-request'

let pendingFaqRequest = null

function normalizeQuestionIndex(value) {
  const nextValue = Number.parseInt(String(value || ''), 10)
  return Number.isFinite(nextValue) && nextValue > 0 ? nextValue : 1
}

export function requestOpenFaqQuestion(questionIndex = 1) {
  const request = {
    questionIndex: normalizeQuestionIndex(questionIndex),
    requestKey: Date.now(),
  }

  pendingFaqRequest = request

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new window.CustomEvent(OPEN_FAQ_REQUEST_EVENT, { detail: request }))
  }

  return request
}

export function consumePendingFaqRequest() {
  const request = pendingFaqRequest
  pendingFaqRequest = null
  return request
}
