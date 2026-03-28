const SHOWCASE_ROW_SIZE = 5
const SHOWCASE_MAX_ITEMS = SHOWCASE_ROW_SIZE * 2

function toShowcaseSlot(slot) {
  const parsedSlot = Number(slot)
  if (!Number.isInteger(parsedSlot)) {
    return null
  }
  if (parsedSlot < 1 || parsedSlot > SHOWCASE_MAX_ITEMS) {
    return null
  }
  return parsedSlot
}

export function splitShowcaseRows(items) {
  const normalizedItems = Array.isArray(items) ? items.filter(Boolean) : []
  const indexedItems = normalizedItems.map((item, index) => ({
    item,
    index,
    slot: toShowcaseSlot(item?.slot),
  }))
  const hasExplicitSlots = indexedItems.some(({ slot }) => slot !== null)

  if (!hasExplicitSlots) {
    return {
      firstRow: normalizedItems.slice(0, SHOWCASE_ROW_SIZE),
      secondRow: normalizedItems.slice(SHOWCASE_ROW_SIZE, SHOWCASE_MAX_ITEMS),
    }
  }

  const firstRow = indexedItems
    .filter(({ slot }) => slot !== null && slot <= SHOWCASE_ROW_SIZE)
    .sort((left, right) => left.slot - right.slot)
    .map(({ item }) => item)
  const secondRow = indexedItems
    .filter(({ slot }) => slot !== null && slot > SHOWCASE_ROW_SIZE)
    .sort((left, right) => left.slot - right.slot)
    .map(({ item }) => item)
  const unslottedItems = indexedItems
    .filter(({ slot }) => slot === null)
    .sort((left, right) => left.index - right.index)
    .map(({ item }) => item)

  const firstRowCapacity = Math.max(0, SHOWCASE_ROW_SIZE - firstRow.length)
  const secondRowCapacity = Math.max(0, SHOWCASE_ROW_SIZE - secondRow.length)

  return {
    firstRow: [...firstRow, ...unslottedItems.slice(0, firstRowCapacity)],
    secondRow: [
      ...secondRow,
      ...unslottedItems.slice(firstRowCapacity, firstRowCapacity + secondRowCapacity),
    ],
  }
}
