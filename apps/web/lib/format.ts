const localDateTimeOptions: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

function parseApiDateTime(value: string): Date {
  const trimmed = value.trim();
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
  const normalized = hasExplicitTimezone ? trimmed : `${trimmed}Z`;
  return new Date(normalized);
}

export function formatLocalDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-AU", localDateTimeOptions).format(date);
}
