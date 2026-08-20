import { useState } from 'react'
import { ChevronDown, ChevronRight, Info } from 'lucide-react'

/**
 * "Як користуватись" — the page explained in its own terms (WB-ALERTS-1).
 *
 * Written because a human has to be able to open this page cold and know what
 * to do. The groups below are exception-first and ordered by urgency, which is
 * not self-evident from the headings alone; and the `no_data` group in
 * particular reads as alarming when it is usually nothing — 43 of the 45
 * parcels that ever went dark came back on their own within 1-5 days
 * (`docs/reviews/2026-08-20-wb-track-no-data-checkpoint.md`).
 *
 * Collapsed by default: it is reference material, not something to read twice.
 * The collapsible idiom matches `TrackingGroup` rather than introducing a
 * primitive — there is no Collapsible in `components/ui/`.
 */
export function UsageNote() {
  const [open, setOpen] = useState(false)
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <Chevron className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
        <Info className="h-4 w-4 shrink-0 text-blue-400" aria-hidden />
        <span className="text-sm font-semibold text-zinc-200">
          Як користуватись
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-zinc-800/60 px-4 py-4 text-sm leading-relaxed text-zinc-400">
          <p className="font-semibold text-zinc-200">
            Як користуватись цією сторінкою
          </p>

          <p>
            Сторінка сама сортує посилки: щодня ми опитуємо Нову Пошту і
            розкладаємо все по групах. Дивитись треба зверху вниз — що вище, то
            важливіше.
          </p>

          <ul className="space-y-2 pl-4">
            <li className="list-disc">
              <strong className="text-zinc-200">
                Потребують уваги (Needs attention)
              </strong>{' '}
              — єдина група для щоденного перегляду. Порядок: невдалі вручення →
              без даних → найбільш прострочені.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">
                Невдале вручення (код 111)
              </strong>{' '}
              — кур'єр не зміг вручити. Дія: одразу написати клієнту.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">Прострочені (Overdue)</strong> —
              обіцяний Новою Поштою строк минув. Часто посилка вже{' '}
              <em>прибула і чекає отримувача</em> — читай останній статус; якщо
              там «очікуйте повідомлення про прибуття» — нагадай клієнту забрати
              замовлення.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">Без даних (No data)</strong> —
              Нова Пошта тимчасово не віддає інформацію. Це нормально: майже
              завжди дані повертаються самі за 1–5 днів, посилка при цьому їде
              далі. Діяти треба лише якщо посилка «темна» понад 6 днів — тоді
              з'явиться сповіщення на головній сторінці; глянь її в кабінеті
              WesternBid.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">Untracked (UPS/USPS)</strong> —
              цих перевізників ми не вміємо опитувати автоматично. Номер посилки
              показано — перевіряй на сайті перевізника вручну.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">In transit / Delivered</strong> —
              згорнуті групи, туди зазирати не обов'язково: все їде або вже
              доставлено.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">Refresh now</strong> —
              позачергове опитування Нової Пошти (не частіше ніж раз на 5
              хвилин). Внизу в рядку кожної посилки можна розгорнути повну
              історію статусів.
            </li>
            <li className="list-disc">
              <strong className="text-zinc-200">Сповіщення на головній</strong> —
              найважливіші події (невдале вручення, посилка без даних понад 6
              днів, довго прострочена, стара неопитувана) самі з'являються на
              головній сторінці CRM. Сповіщення зникає само, коли проблема
              вирішилась, або знімається кнопкою «Опрацьовано» (фіксується, хто
              і коли зняв).
            </li>
          </ul>
        </div>
      )}
    </section>
  )
}
