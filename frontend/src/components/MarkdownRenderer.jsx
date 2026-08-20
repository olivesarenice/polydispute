import React from "react";

/**
 * Parses inline markdown tokens: bold, italic, inline code, links, strikethrough, urls.
 */
function renderInline(text) {
  if (!text) return null;

  // Regex splitting by: [text](url), `code`, **bold**, *italic*, ~~strike~~, or raw URLs
  const regex = /(\[.*?\]\(https?:\/\/[^\s)]+\)|`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|~~[^~]+~~|https?:\/\/[^\s<)]+)/g;
  const parts = text.split(regex);

  return parts.map((part, i) => {
    if (!part) return null;

    // Link: [text](url)
    const linkMatch = part.match(/^\[(.*?)\]\((https?:\/\/[^\s)]+)\)$/);
    if (linkMatch) {
      return (
        <a
          key={i}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 break-all"
        >
          {linkMatch[1]}
        </a>
      );
    }

    // Raw URL
    if (part.startsWith("http://") || part.startsWith("https://")) {
      return (
        <a
          key={i}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 break-all"
        >
          {part}
        </a>
      );
    }

    // Inline Code: `code`
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return (
        <code
          key={i}
          className="rounded bg-slate-900 px-1 py-0.5 font-mono text-[10px] text-emerald-300 border border-slate-700/80"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    // Bold: **text** or __text__
    if ((part.startsWith("**") && part.endsWith("**") && part.length >= 4) ||
        (part.startsWith("__") && part.endsWith("__") && part.length >= 4)) {
      return <strong key={i} className="font-bold text-slate-100">{part.slice(2, -2)}</strong>;
    }

    // Italic: *text* or _text_
    if ((part.startsWith("*") && part.endsWith("*") && part.length >= 2) ||
        (part.startsWith("_") && part.endsWith("_") && part.length >= 2)) {
      return <em key={i} className="italic text-slate-200">{part.slice(1, -1)}</em>;
    }

    // Strikethrough: ~~text~~
    if (part.startsWith("~~") && part.endsWith("~~") && part.length >= 4) {
      return <del key={i} className="line-through text-slate-500">{part.slice(2, -2)}</del>;
    }

    return part;
  });
}

/**
 * Lightweight, zero-dependency Markdown Renderer for Discord / Discourse Chat Stream
 */
export default function MarkdownRenderer({ content, className = "" }) {
  if (!content) return null;

  const lines = content.split("\n");
  const blocks = [];
  let inCodeBlock = false;
  let codeLines = [];
  let codeLang = "";

  lines.forEach((line, idx) => {
    // Code block toggle
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        // Close code block
        blocks.push({
          type: "code",
          content: codeLines.join("\n"),
          lang: codeLang,
          key: `code-${idx}`,
        });
        codeLines = [];
        codeLang = "";
        inCodeBlock = false;
      } else {
        // Open code block
        inCodeBlock = true;
        codeLang = line.trim().slice(3).trim();
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    const trimmed = line.trim();

    // Headers
    if (trimmed.startsWith("### ")) {
      blocks.push({ type: "h3", content: trimmed.slice(4), key: `h3-${idx}` });
    } else if (trimmed.startsWith("## ")) {
      blocks.push({ type: "h2", content: trimmed.slice(3), key: `h2-${idx}` });
    } else if (trimmed.startsWith("# ")) {
      blocks.push({ type: "h1", content: trimmed.slice(2), key: `h1-${idx}` });
    }
    // Blockquote
    else if (trimmed.startsWith("> ")) {
      blocks.push({ type: "quote", content: trimmed.slice(2), key: `q-${idx}` });
    }
    // Bullet item
    else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      blocks.push({ type: "bullet", content: trimmed.slice(2), key: `b-${idx}` });
    }
    // Numbered item (e.g. 1. text)
    else if (/^\d+\.\s/.test(trimmed)) {
      const match = trimmed.match(/^\d+\.\s(.*)/);
      blocks.push({ type: "number", content: match ? match[1] : trimmed, key: `n-${idx}` });
    }
    // Regular paragraph / blank line
    else if (trimmed.length > 0) {
      blocks.push({ type: "p", content: line, key: `p-${idx}` });
    } else {
      blocks.push({ type: "br", key: `br-${idx}` });
    }
  });

  // Flush open code block if unclosed
  if (inCodeBlock && codeLines.length > 0) {
    blocks.push({
      type: "code",
      content: codeLines.join("\n"),
      lang: codeLang,
      key: `code-unclosed`,
    });
  }

  return (
    <div className={`space-y-1 text-slate-300 text-[11px] leading-relaxed break-words font-sans ${className}`}>
      {blocks.map((b) => {
        switch (b.type) {
          case "h1":
            return (
              <h4 key={b.key} className="text-xs font-bold text-slate-100 border-b border-slate-800 pb-0.5 mt-1">
                {renderInline(b.content)}
              </h4>
            );
          case "h2":
            return (
              <h5 key={b.key} className="text-[11.5px] font-bold text-slate-200 mt-1">
                {renderInline(b.content)}
              </h5>
            );
          case "h3":
            return (
              <h6 key={b.key} className="text-[11px] font-semibold text-slate-300 mt-0.5">
                {renderInline(b.content)}
              </h6>
            );
          case "quote":
            return (
              <div key={b.key} className="border-l-2 border-emerald-500/60 pl-2 py-0.5 text-slate-400 italic bg-slate-900/30 rounded-r">
                {renderInline(b.content)}
              </div>
            );
          case "bullet":
            return (
              <div key={b.key} className="flex items-start gap-1.5 pl-1.5">
                <span className="text-emerald-400 font-bold text-[9px] select-none mt-0.5">&bull;</span>
                <span className="flex-1">{renderInline(b.content)}</span>
              </div>
            );
          case "number":
            return (
              <div key={b.key} className="flex items-start gap-1.5 pl-1.5">
                <span className="text-slate-400 font-mono text-[9.5px] select-none mt-0.5">1.</span>
                <span className="flex-1">{renderInline(b.content)}</span>
              </div>
            );
          case "code":
            return (
              <pre
                key={b.key}
                className="overflow-x-auto rounded bg-slate-950 p-2 font-mono text-[10px] text-emerald-300 border border-slate-800"
              >
                <code>{b.content}</code>
              </pre>
            );
          case "br":
            return <div key={b.key} className="h-0.5" />;
          case "p":
          default:
            return (
              <p key={b.key} className="text-slate-300">
                {renderInline(b.content)}
              </p>
            );
        }
      })}
    </div>
  );
}
