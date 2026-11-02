/** The Counsellor's icon: a chat bubble holding a filled heart, drawn like the other (lucide) nav icons. */
export default function CounselIcon({ className = "h-5 w-5", strokeWidth = 2, ...rest }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" className={className} {...rest}>
      <path d="M12 3c5 0 9 3.4 9 7.7s-4 7.7-9 7.7c-1 0-2-.1-2.9-.4L4.5 20l1.2-3.6C4 15 3 13 3 10.7 3 6.4 7 3 12 3Z" />
      <path fill="currentColor" stroke="none"
        d="M12 14.4c-.2 0-.4-.1-.5-.2C9.6 12.7 8.4 11.7 8.4 10.3c0-1.1.9-1.9 1.9-1.9.7 0 1.3.3 1.7.9.4-.6 1-.9 1.7-.9 1 0 1.9.8 1.9 1.9 0 1.4-1.2 2.4-3.1 3.9-.1.1-.3.2-.5.2Z" />
    </svg>
  );
}
