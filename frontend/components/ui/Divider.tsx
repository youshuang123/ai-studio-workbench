export function Divider({ className = "" }: { className?: string }) {
  return <hr className={`border-0 border-t border-divider ${className}`.trim()} />;
}

export function Hairline({ className = "" }: { className?: string }) {
  return <hr className={`border-0 border-t border-hairline ${className}`.trim()} />;
}
