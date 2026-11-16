/** 공용 화면 부품 — Universal Design DNA의 상태·치수 규칙을 따른다. 색·간격·반경은 tokens.css의 토큰만 쓴다. */

import * as RD from "@radix-ui/react-dialog";
import { CircleAlert, CircleCheck, Info, LoaderCircle, TriangleAlert, X } from "lucide-react";
import { useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent, type ReactNode, type SelectHTMLAttributes } from "react";
import { arrow, direction } from "@/lib/format";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ── 버튼 ────────────────────────────────────────────────────────────────
// primary(잉크)는 화면의 목적이 되는 행동 하나에만. 색(accent)으로 버튼을 칠하지 않는다.

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover",
  secondary: "bg-secondary text-ink hover:bg-secondary-hover",
  outline: "border border-border bg-surface text-ink hover:bg-secondary",
  ghost: "text-ink-secondary hover:bg-secondary hover:text-ink",
  danger: "bg-danger text-on-danger hover:bg-danger-hover",
};
const SIZE: Record<Size, string> = {
  sm: "h-8 gap-1 px-3 text-label",
  md: "h-10 gap-2 px-4 text-button",
  lg: "h-12 gap-2 px-5 text-button",
  icon: "size-10",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "secondary", size = "md", busy = false, icon, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "tap inline-flex shrink-0 items-center justify-center rounded-md font-semibold whitespace-nowrap transition-[background-color,color,scale] duration-(--duration-fast) active:scale-98 disabled:opacity-40 disabled:active:scale-100",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {busy ? <Spinner /> : icon}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle aria-hidden className={cx("spin size-4", className)} />;
}

// ── 표시 ────────────────────────────────────────────────────────────────

export type Tone = "neutral" | "outline" | "accent" | "success" | "warning" | "danger" | "up" | "down";
const BADGE: Record<Tone, string> = {
  neutral: "bg-secondary text-ink",
  outline: "border border-border text-ink-secondary",
  accent: "bg-accent-subtle text-ink",
  success: "bg-success-subtle text-ink",
  warning: "bg-warning-subtle text-ink",
  danger: "bg-danger-subtle text-ink",
  // 가격 방향(매수·매도 포함)은 글자색으로도 구분한다
  up: "bg-up-subtle text-up",
  down: "bg-down-subtle text-down",
};
const DOT: Partial<Record<Tone, string>> = { accent: "bg-accent", success: "bg-success", warning: "bg-warning", danger: "bg-danger" };

/** 한두 단어의 상태·분류 표시. 상태는 단어가 말하고, 색 점은 거든다. */
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex h-6 items-center gap-1 rounded-full px-2 text-label font-medium whitespace-nowrap", BADGE[tone], className)}>
      {DOT[tone] && <span aria-hidden className={cx("size-2 shrink-0 rounded-full", DOT[tone])} />}
      {children}
    </span>
  );
}

/** 등락 표시: 색과 함께 ▲▼ 기호를 붙여 색을 못 봐도 읽힌다. 상승은 빨강, 하락은 파랑(국내 관례). */
export function Delta({ value, children, className }: { value: number | null | undefined; children: ReactNode; className?: string }) {
  const dir = direction(value);
  return (
    <span className={cx("num whitespace-nowrap", dir === "up" ? "text-up" : dir === "down" ? "text-down" : "text-ink-secondary", className)}>
      {dir !== "flat" && (
        <span aria-hidden className="mr-1">
          {arrow(value)}
        </span>
      )}
      {children}
    </span>
  );
}

/** 하나의 대상을 묶는 표면. 그림자 대신 헤어라인 외곽선으로 구분한다. */
export function Panel({ title, actions, children, className, bodyClassName }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string }) {
  return (
    <section className={cx("rounded-lg border border-divider bg-surface", className)}>
      {(title || actions) && (
        <header className="flex min-h-12 flex-wrap items-center justify-between gap-2 border-b border-divider px-4 py-2">
          {title && <h2 className="text-h6 font-semibold text-ink">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName ?? "p-4"}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, lead, actions }: { title: string; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-h3 font-bold text-ink lg:text-h2">{title}</h1>
        {lead && <p className="mt-2 max-w-reading text-body-sm text-ink-secondary">{lead}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** 수치 하나: 위쪽 잉크 룰, 라벨, 값, 기준·출처. */
export function Stat({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0 border-t border-ink pt-2">
      <dt className="text-label font-medium text-ink-muted">{label}</dt>
      <dd className="num mt-1 text-h5 font-semibold text-ink">{children}</dd>
      {hint && <dd className="num text-caption text-ink-muted">{hint}</dd>}
    </div>
  );
}

// ── 상태 화면 ───────────────────────────────────────────────────────────

/** 빈 상태: 지금 상태를 사실대로, 왜 비었고 무엇을 하면 되는지. 왼쪽 정렬이 기본이다. */
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="p-4">
      <p className="text-h6 font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 max-w-reading text-body-sm text-ink-secondary">{children}</p>}
      {action && <div className="mt-3 text-body-sm font-semibold text-ink">{action}</div>}
    </div>
  );
}

type AlertTone = "neutral" | "accent" | "success" | "warning" | "danger";
const ALERT: Record<AlertTone, { bg: string; icon: string; Icon: typeof Info }> = {
  neutral: { bg: "bg-surface-sunken", icon: "text-ink-secondary", Icon: Info },
  accent: { bg: "bg-accent-subtle", icon: "text-accent", Icon: Info },
  success: { bg: "bg-success-subtle", icon: "text-success", Icon: CircleCheck },
  warning: { bg: "bg-warning-subtle", icon: "text-warning", Icon: TriangleAlert },
  danger: { bg: "bg-danger-subtle", icon: "text-danger", Icon: CircleAlert },
};

/** 계속 보여야 하는 상태 메시지. 옅은 바탕 + 톤 색 아이콘 + 잉크 글자(색만으로 뜻을 전하지 않는다). */
export function Notice({ tone = "neutral", children, action }: { tone?: AlertTone; children: ReactNode; action?: ReactNode }) {
  const { bg, icon, Icon } = ALERT[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex flex-wrap items-start gap-x-3 gap-y-2 rounded-lg px-4 py-3 text-body-sm text-ink", bg)}>
      <Icon aria-hidden className={cx("mt-1 size-4 shrink-0", icon)} />
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Notice
      tone="danger"
      action={
        onRetry && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            다시 시도
          </Button>
        )
      }
    >
      {message}
    </Notice>
  );
}

export function SkeletonRows({ rows = 5, label = "불러오는 중" }: { rows?: number; label?: string }) {
  const widths = ["w-11/12", "w-10/12", "w-9/12"];
  return (
    <div role="status" aria-busy="true" aria-label={label} className="space-y-2 p-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={cx("skeleton h-8", widths[i % 3])} />
      ))}
    </div>
  );
}

// ── 입력 ────────────────────────────────────────────────────────────────

const CONTROL =
  "tap h-10 w-full rounded-md border border-border bg-surface px-3 text-body-sm text-ink placeholder:text-ink-muted transition-colors duration-(--duration-fast) hover:border-ink-secondary focus-visible:border-focus focus-visible:outline-offset-0 disabled:bg-surface-sunken disabled:opacity-40 aria-[invalid=true]:border-danger";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}

export function Field({ label, hint, error, className, children }: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-label font-medium text-ink">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1 flex items-center gap-1 text-label text-danger">
          <CircleAlert aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="mt-1 text-caption text-ink-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(CONTROL, className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(CONTROL, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export function Check({ label, hint, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }) {
  return (
    <label className={cx("flex min-h-11 cursor-pointer items-start gap-3 py-2", className)}>
      <input type="checkbox" className="mt-1 size-4 shrink-0 accent-accent" {...rest} />
      <span className="min-w-0">
        <span className="block text-body-sm text-ink">{label}</span>
        {hint && <span className="block text-caption text-ink-muted">{hint}</span>}
      </span>
    </label>
  );
}

/** 서로 배타적인 2~5개 선택지. */
export function RadioRow<T extends string>({ legend, name, value, onChange, options, disabled }: { legend: string; name: string; value: T; onChange: (value: T) => void; options: { value: T; label: ReactNode }[]; disabled?: boolean }) {
  return (
    <fieldset disabled={disabled} className="flex flex-wrap gap-x-6 gap-y-1">
      <legend className="sr-only">{legend}</legend>
      {options.map((option) => (
        <label key={option.value} className="flex min-h-11 cursor-pointer items-center gap-2 text-body-sm text-ink">
          <input type="radio" name={name} className="size-4 accent-accent" checked={value === option.value} onChange={() => onChange(option.value)} />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}

/** 필터처럼 나란히 놓이는 토글 버튼 묶음(탭이 아니다). */
export function ToggleGroup<T extends string>({ value, onChange, options, label }: { value: T; onChange: (value: T) => void; options: { value: T; label: ReactNode }[]; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex max-w-full gap-2 overflow-x-auto p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cx(
            "tap h-8 shrink-0 rounded-md border px-3 text-label whitespace-nowrap transition-colors duration-(--duration-fast)",
            value === option.value ? "border-ink bg-secondary font-semibold text-ink" : "border-border bg-surface font-medium text-ink-secondary hover:bg-secondary hover:text-ink",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** 같은 맥락 안의 보기 전환. 선택은 잉크 글자와 2px 잉크 밑줄. ← → Home End로 이동한다. */
export function Tabs<T extends string>({ value, onChange, items, label }: { value: T; onChange: (value: T) => void; items: { value: T; label: ReactNode }[]; label: string }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = items.length - 1;
    const next = event.key === "ArrowRight" ? (index === last ? 0 : index + 1) : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1) : event.key === "Home" ? 0 : event.key === "End" ? last : -1;
    if (next < 0) return;
    event.preventDefault();
    onChange(items[next].value);
    refs.current[items[next].value]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="flex max-w-full gap-6 overflow-x-auto border-b border-divider">
      {items.map((item, index) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(node) => {
              refs.current[item.value] = node;
            }}
            type="button"
            role="tab"
            id={`tab-${item.value}`}
            aria-selected={selected}
            aria-controls={`panel-${item.value}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(event) => move(event, index)}
            className={cx(
              "group -mb-px h-11 shrink-0 border-b-2 text-body-sm whitespace-nowrap transition-colors duration-(--duration-base) focus-visible:outline-none",
              selected ? "border-ink font-semibold text-ink" : "border-transparent font-medium text-ink-muted hover:text-ink",
            )}
          >
            {/* 포커스 링은 글자 둘레에 그린다: 탭 전체에 그리면 선택 밑줄을 가린다 */}
            <span className="rounded-xs px-1 py-1 group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-focus">{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── 대화상자 ────────────────────────────────────────────────────────────

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}

/** 흐름을 멈추고 결정을 요구하는 모달. 블러 없는 scrim, 떠 있는 표면. */
export function Modal({ open, onOpenChange, title, description, children, wide = false }: ModalProps) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-(--z-overlay) bg-scrim data-[state=open]:enter-fade" />
        <RD.Content
          className={cx(
            "fixed top-1/2 left-1/2 z-(--z-modal) max-h-[88dvh] w-[calc(100vw-var(--space-8))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-surface-raised p-6 shadow-3 data-[state=open]:enter-dialog",
            wide ? "max-w-180" : "max-w-130",
          )}
        >
          <div className="mb-2 flex items-start justify-between gap-3">
            <RD.Title className="text-h5 font-semibold text-ink">{title}</RD.Title>
            <RD.Close aria-label="닫기" className="-mt-2 -mr-2 grid size-10 shrink-0 place-items-center rounded-md text-ink-secondary transition-colors duration-(--duration-fast) hover:bg-secondary hover:text-ink">
              <X aria-hidden className="size-5" />
            </RD.Close>
          </div>
          {description ? <RD.Description className="mb-4 text-body-sm text-ink-secondary">{description}</RD.Description> : <RD.Description className="sr-only">{title}</RD.Description>}
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

// ── 표 공용 클래스(세로선·줄무늬 없이 헤어라인 행 구분, 숫자는 오른쪽 정렬) ──

export const TH = "h-10 border-b border-border px-3 text-left text-label font-medium whitespace-nowrap text-ink-muted";
export const TD = "h-10 border-b border-divider px-3 py-2 text-body-sm text-ink";
export const TDR = `${TD} num text-right whitespace-nowrap`;
export const THR = `${TH} text-right`;
