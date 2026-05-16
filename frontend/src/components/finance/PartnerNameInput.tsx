import { useEffect, useRef, useState } from 'react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface PartnerNameInputProps {
  value: string
  onChange: (next: string) => void
  suggestions: string[]
  placeholder?: string
  disabled?: boolean
  autoFocus?: boolean
}

export default function PartnerNameInput({
  value,
  onChange,
  suggestions,
  placeholder = 'Partner name',
  disabled,
  autoFocus,
}: PartnerNameInputProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const lowerValue = value.trim().toLowerCase()
  const filtered = suggestions.filter(
    (s) =>
      s.toLowerCase() !== lowerValue && s.toLowerCase().includes(lowerValue),
  )

  return (
    <div ref={containerRef} className="relative">
      <Input
        autoFocus={autoFocus}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        className="border-zinc-800 bg-zinc-900/50"
      />
      {open && filtered.length > 0 && (
        <div
          className={cn(
            'absolute left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md',
            'border border-zinc-800 bg-zinc-950 shadow-xl shadow-black/40',
          )}
        >
          {filtered.map((name) => (
            <button
              key={name}
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800"
              onClick={() => {
                onChange(name)
                setOpen(false)
              }}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
