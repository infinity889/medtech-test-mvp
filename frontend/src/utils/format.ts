import type { ServiceCategory } from '../api/types';

const kztIntFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
});

const kztDecimalFormatter = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const exactDateFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const shortDateFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: 'short',
});

const CATEGORY_LABELS: Record<ServiceCategory, string> = {
  lab: 'Анализы',
  doctor: 'Приём врачей',
  diagnostics: 'Диагностика',
  procedure: 'Процедуры',
};

export function categoryLabelRu(category: ServiceCategory): string {
  return CATEGORY_LABELS[category];
}

export function formatPriceKzt(amount: number): string {
  const isWhole = Math.abs(amount - Math.round(amount)) < 0.005;
  const formatted = isWhole ? kztIntFormatter.format(amount) : kztDecimalFormatter.format(amount);
  return `${formatted}\u00a0₸`;
}

export function formatDurationDays(days: number | null): string {
  if (days === null || days === undefined) {
    return 'Уточняйте в клинике';
  }
  if (days === 0) {
    return 'В день обращения';
  }
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return `${days} день`;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${days} дня`;
  }
  return `${days} дней`;
}

export function formatDistanceKm(distanceKm: number | null): string | null {
  if (distanceKm === null || distanceKm === undefined) {
    return null;
  }
  if (distanceKm < 1) {
    return `${Math.round(distanceKm * 1000)} м`;
  }
  return `${distanceKm.toFixed(1)} км`;
}

export function formatExactDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return exactDateFormatter.format(date);
}

export function formatShortDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return shortDateFormatter.format(date);
}

export function formatFreshness(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return 'Недавно';
  }
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.max(0, Math.floor(diffMs / 60_000));
  if (diffMin < 60) {
    return diffMin <= 1 ? 'только что' : `${diffMin} мин назад`;
  }
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) {
    return `${diffHours} ч назад`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays <= 30) {
    return `${diffDays} дн назад`;
  }
  return exactDateFormatter.format(date);
}
