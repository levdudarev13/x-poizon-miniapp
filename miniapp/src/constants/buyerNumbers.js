const BUYER_EMPTY_VALUE = '\u2014'

function normalizeBuyerInteger(value) {
  if (value == null) {
    return null
  }

  const number = Number(value)

  if (!Number.isFinite(number)) {
    return null
  }

  return Math.round(number)
}

export function formatBuyerRub(value) {
  const number = normalizeBuyerInteger(value)
  return number == null ? BUYER_EMPTY_VALUE : `${number.toLocaleString('ru-RU')}\u00A0\u20BD`
}

export function formatBuyerCny(value) {
  const number = normalizeBuyerInteger(value)
  return number == null ? BUYER_EMPTY_VALUE : `${number.toLocaleString('ru-RU')}\u00A0\u00A5`
}

export function formatBuyerNumber(value) {
  const number = normalizeBuyerInteger(value)
  return number == null ? BUYER_EMPTY_VALUE : number.toLocaleString('ru-RU')
}
