/** Render supplied explanations as text; ordered checks remain keyboard readable. */
export default function ExplanationText({ text, ordered = false }) {
  const lines = text.split('\n').filter((line) => line.trim());
  const checks = [];
  if (ordered) {
    for (const line of lines) {
      const match = line.match(/^(\d+)\.\s+(.*)$/);
      if (!match || Number(match[1]) !== checks.length + 1) break;
      checks.push(match[2]);
    }
  }
  return <div className="oi-explanation-text">
    {!!checks.length && <ol>{checks.map((line, index) => <li key={index}>{line}</li>)}</ol>}
    {lines.slice(checks.length).map((line, index) => <p key={index}>{line}</p>)}
  </div>;
}
