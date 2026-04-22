import { djb2Hash } from './shopTheme'

const AVATAR_PALETTE = [
  'bg-teal-500', 'bg-violet-500', 'bg-amber-500', 'bg-blue-500',
  'bg-pink-500', 'bg-cyan-500', 'bg-orange-500', 'bg-rose-500',
]

export function getInitials(name: string): string {
  // "Mary Mullins (mmullins4135)" → "MM"
  // "9ccstar" → "9C"
  const words = name.replace(/\(.*\)/, '').trim().split(' ')
  if (words.length === 1) {
    const word = words[0]
    return word.substring(0, 2).toUpperCase()
  }
  return words.slice(0, 2).map(w => w[0]?.toUpperCase() ?? '').join('')
}

export function getAvatarColor(name: string): string {
  const index = djb2Hash(name) % AVATAR_PALETTE.length
  return AVATAR_PALETTE[index]
}
