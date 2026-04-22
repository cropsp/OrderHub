// Deterministic color assignment for shops based on name/id
// Same approach as getAvatarColor() used for customers

const SHOP_PALETTE = [
  { text: 'text-teal-400',   bg: 'bg-teal-400/10',   dot: 'bg-teal-400'   },
  { text: 'text-violet-400', bg: 'bg-violet-400/10', dot: 'bg-violet-400' },
  { text: 'text-amber-400',  bg: 'bg-amber-400/10',  dot: 'bg-amber-400'  },
  { text: 'text-blue-400',   bg: 'bg-blue-400/10',   dot: 'bg-blue-400'   },
  { text: 'text-pink-400',   bg: 'bg-pink-400/10',   dot: 'bg-pink-400'   },
  { text: 'text-cyan-400',   bg: 'bg-cyan-400/10',   dot: 'bg-cyan-400'   },
  { text: 'text-orange-400', bg: 'bg-orange-400/10', dot: 'bg-orange-400' },
  { text: 'text-rose-400',   bg: 'bg-rose-400/10',   dot: 'bg-rose-400'   },
]

export function djb2Hash(str: string): number {
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 33) ^ str.charCodeAt(i)
  }
  return Math.abs(hash)
}

export function getShopTheme(shopNameOrId: string) {
  const index = djb2Hash(shopNameOrId) % SHOP_PALETTE.length
  return SHOP_PALETTE[index]
}
