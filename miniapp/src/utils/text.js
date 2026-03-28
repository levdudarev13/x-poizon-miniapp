const CP1251_SPECIAL_BYTES = new Map([
  ['Ђ', 0x80], ['Ѓ', 0x81], ['‚', 0x82], ['ѓ', 0x83], ['„', 0x84], ['…', 0x85], ['†', 0x86], ['‡', 0x87],
  ['€', 0x88], ['‰', 0x89], ['Љ', 0x8a], ['‹', 0x8b], ['Њ', 0x8c], ['Ќ', 0x8d], ['Ћ', 0x8e], ['Џ', 0x8f],
  ['ђ', 0x90], ['‘', 0x91], ['’', 0x92], ['“', 0x93], ['”', 0x94], ['•', 0x95], ['–', 0x96], ['—', 0x97],
  ['™', 0x99], ['љ', 0x9a], ['›', 0x9b], ['њ', 0x9c], ['ќ', 0x9d], ['ћ', 0x9e], ['џ', 0x9f],
  ['Ў', 0xa1], ['ў', 0xa2], ['Ј', 0xa3], ['Ґ', 0xa5], ['Ё', 0xa8], ['Є', 0xaa], ['Ї', 0xaf],
  ['°', 0xb0], ['І', 0xb2], ['і', 0xb3], ['ґ', 0xb4], ['µ', 0xb5], ['ё', 0xb8], ['№', 0xb9], ['є', 0xba],
  ['ј', 0xbc], ['Ѕ', 0xbd], ['ѕ', 0xbe], ['ї', 0xbf],
])

function getCp1251Byte(char) {
  const codePoint = char.codePointAt(0)

  if (codePoint <= 0xff) {
    return codePoint
  }

  if (codePoint >= 0x0410 && codePoint <= 0x044f) {
    return codePoint - 0x350
  }

  return CP1251_SPECIAL_BYTES.get(char)
}

export function repairMojibakeText(value) {
  const text = String(value ?? '')
  if (!text || ![...text].some((char) => char.charCodeAt(0) > 127)) {
    return text
  }

  const bytes = []
  for (const char of text) {
    const byte = getCp1251Byte(char)
    if (byte == null) {
      return text
    }
    bytes.push(byte)
  }

  try {
    const repaired = new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(bytes))
    return repaired !== text ? repaired : text
  } catch {
    return text
  }
}

export function repairMojibakeDeep(value) {
  if (typeof value === 'string') {
    return repairMojibakeText(value)
  }

  if (Array.isArray(value)) {
    return value.map(repairMojibakeDeep)
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        typeof key === 'string' ? repairMojibakeText(key) : key,
        repairMojibakeDeep(item),
      ]),
    )
  }

  return value
}

export function parseRepairJson(value, fallback = null) {
  try {
    return repairMojibakeDeep(JSON.parse(value))
  } catch {
    return fallback
  }
}
