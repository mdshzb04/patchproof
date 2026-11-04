const TOKEN =
  /(#.*$)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|\b(import|from|def|return|if|elif|else|for|while|try|except|finally|pass|with|as|class|None|True|False|in|not|and|or|lambda|yield|raise|async|await|global|nonlocal)\b/g;

export function LineText({ text }: { text: string }) {
  const parts: { kind: string; text: string }[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ kind: "", text: text.slice(last, index) });
    const raw = match[0];
    const kind = match[1] ? "cmt" : match[2] ? "str" : "kw";
    parts.push({ kind, text: raw });
    last = index + raw.length;
  }
  if (last < text.length) parts.push({ kind: "", text: text.slice(last) });
  if (parts.length === 0) parts.push({ kind: "", text: text || " " });
  return (
    <>
      {parts.map((part, index) =>
        part.kind ? (
          <span key={index} className={`tok tok-${part.kind}`}>
            {part.text}
          </span>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}
