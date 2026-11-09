import { Children, isValidElement, useEffect, useState } from 'react';
const messageText = value => Children.toArray(value).map(child => isValidElement(child) ? messageText(child.props.children) : String(child)).join('');
export default function TemporaryMessage({ children, className = '', role = 'status' }) {
  const [visible, setVisible] = useState(true);
  const text = messageText(children);
  useEffect(() => {
    setVisible(true);
    const timeout = setTimeout(() => setVisible(false), className.includes('error') ? 8000 : 4000);
    return () => clearTimeout(timeout);
  }, [text, className]);
  if (!visible || !children) return null;
  return <div className={`message ${className}`} role={role}><span>{children}</span><button className="message-close" type="button" aria-label="Dismiss message" onClick={() => setVisible(false)}>×</button></div>;
}
