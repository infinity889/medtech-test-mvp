import { Search, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { fetchAutocomplete } from '../api/client';
import type { ServiceAutocompleteItem, ServiceCategory } from '../api/types';
import { categoryLabelRu, formatPriceKzt } from '../utils/format';

interface SearchBarProps {
  value: string;
  city?: string;
  category?: ServiceCategory;
  onTextChange: (nextText: string) => void;
  onSelectService: (item: ServiceAutocompleteItem) => void;
  onSubmitSearch: (queryText: string) => void;
  onClear: () => void;
}

const POPULAR_QUERIES = ['ОАК', 'Витамин D', 'ТТГ', 'Биохимия', 'Приём терапевта', 'УЗИ'] as const;

export function SearchBar({
  value,
  city,
  category,
  onTextChange,
  onSelectService,
  onSubmitSearch,
  onClear,
}: SearchBarProps) {
  const [suggestions, setSuggestions] = useState<ServiceAutocompleteItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isFetching, setIsFetching] = useState(false);

  const listboxId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = value.trim();
    if (trimmed.length < 1) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setIsFetching(true);
      try {
        const res = await fetchAutocomplete(
          { q: trimmed, city: city || undefined, category, limit: 8 },
          controller.signal,
        );
        setSuggestions(res.items);
        setActiveIndex(-1);
        setIsOpen(res.items.length > 0);
      } catch {
        if (!controller.signal.aborted) {
          setSuggestions([]);
          setIsOpen(false);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsFetching(false);
        }
      }
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value, city, category]);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      if (suggestions.length === 0) return;
      event.preventDefault();
      setIsOpen(true);
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
    } else if (event.key === 'ArrowUp') {
      if (suggestions.length === 0) return;
      event.preventDefault();
      setIsOpen(true);
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const activeItem = activeIndex >= 0 ? suggestions[activeIndex] : undefined;
      if (isOpen && activeItem) {
        onSelectService(activeItem);
        setIsOpen(false);
      } else {
        setIsOpen(false);
        onSubmitSearch(value);
      }
    } else if (event.key === 'Escape') {
      setIsOpen(false);
      setActiveIndex(-1);
    }
  }

  return (
    <div ref={containerRef} className="w-full">
      <div className="relative flex items-center">
        <Search
          className="pointer-events-none absolute left-3.5 h-5 w-5 text-ink-subtle"
          aria-hidden="true"
        />
        <input
          type="search"
          role="combobox"
          aria-label="Поиск медицинской услуги"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            activeIndex >= 0 && suggestions[activeIndex]
              ? `${listboxId}-opt-${suggestions[activeIndex].service_id}`
              : undefined
          }
          value={value}
          onChange={(e) => onTextChange(e.target.value)}
          onFocus={() => {
            if (suggestions.length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Например: ОАК, CBC, Витамин D, Приём терапевта, УЗИ…"
          className="h-12 w-full rounded-xl border border-border-strong bg-surface pr-28 pl-11 text-sm text-ink placeholder:text-ink-subtle focus:border-brand focus:outline-none sm:text-base"
        />
        {value ? (
          <button
            type="button"
            onClick={() => {
              onClear();
              setSuggestions([]);
              setIsOpen(false);
            }}
            aria-label="Очистить поиск"
            className="absolute right-24 rounded-lg p-1.5 text-ink-subtle transition hover:bg-surface-subtle hover:text-ink"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => {
            setIsOpen(false);
            onSubmitSearch(value);
          }}
          className="absolute right-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-hover"
        >
          Найти
        </button>

        {isOpen && suggestions.length > 0 ? (
          <ul
            id={listboxId}
            role="listbox"
            aria-label="Подсказки услуг"
            className="absolute top-full right-0 left-0 z-30 mt-1.5 max-h-80 overflow-y-auto rounded-xl border border-border-strong bg-surface py-1.5 shadow-lg"
          >
            {suggestions.map((item, index) => {
              const isActive = index === activeIndex;
              return (
                <li
                  key={item.service_id}
                  id={`${listboxId}-opt-${item.service_id}`}
                  role="option"
                  aria-selected={isActive}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onSelectService(item);
                    setIsOpen(false);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-sm transition ${
                    isActive ? 'bg-brand-soft text-brand' : 'text-ink hover:bg-surface-subtle'
                  }`}
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{item.canonical_name}</p>
                    <p className="mt-0.5 text-xs text-ink-subtle">
                      {categoryLabelRu(item.category)}
                      {item.matched_synonym ? ` · совпало: «${item.matched_synonym}»` : ''}
                    </p>
                  </div>
                  <div className="shrink-0 text-right tabular-nums">
                    {item.min_price_kzt !== null ? (
                      <p className="font-semibold text-savings">
                        от {formatPriceKzt(item.min_price_kzt)}
                      </p>
                    ) : null}
                    <p className="text-xs text-ink-subtle">{item.offers_count} предл.</p>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-ink-subtle">Часто ищут:</span>
        {POPULAR_QUERIES.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() => {
              onTextChange(chip);
              onSubmitSearch(chip);
            }}
            className="rounded-full border border-border bg-surface px-2.5 py-1 font-medium text-ink-muted transition hover:border-brand hover:bg-brand-soft hover:text-brand"
          >
            {chip}
          </button>
        ))}
        {isFetching ? <span className="ml-auto text-ink-subtle">Поиск подсказок…</span> : null}
      </div>
    </div>
  );
}
