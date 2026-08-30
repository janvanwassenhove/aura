/** U272: the memory note, as something a graph can actually show.
 *
 * Asked as "is graph only taking skills into account or also showing memory
 * (these can be eg in other colouring/styling with key words?)", then pinned
 * down with "currently memory is single bullet in graph".
 *
 * That is exactly what it was. Long-term memory is stored as ONE ProfileFact
 * with key "memory" whose value is the whole bullet list, and the graph draws
 * one node per fact — so a person's entire remembered life arrived as a single
 * dot labelled "memory: - Jan is actief en geniet van sporten…", truncated at
 * 40 characters. Everything he had learned, rendered as one bullet.
 *
 * Splitting it is the easy half. The useful half is that a memory line is a
 * sentence, and a sentence makes a terrible node label — so each line is
 * reduced to the words that distinguish it, and words shared by several lines
 * become shared nodes. That is what turns a list into a web: you can see that
 * three separate things he remembers are all about football.
 *
 * No LLM, no network: this runs on every render of a graph the owner is
 * dragging around, and it must be instant and predictable. Crude, honest word
 * frequency beats a clever guess that changes between frames.
 */

/** Words that carry no meaning on a node label. Dutch and English together —
 *  the memory is written in whatever language he was spoken to in, and this
 *  file cannot know which. */
const STOPWORDS = new Set([
  // nl
  'aan', 'als', 'ander', 'andere', 'bij', 'dat', 'deze', 'die', 'dit', 'door',
  'een', 'eens', 'en', 'ergens', 'geen', 'gaat', 'haar', 'heb', 'hebben',
  'heeft', 'het', 'hier', 'hij', 'hun', 'iets', 'ins', 'is', 'kan', 'maar',
  'meer', 'met', 'naar', 'niet', 'nog', 'of', 'om', 'ook', 'op', 'over',
  'te', 'tot', 'uit', 'van', 'veel', 'voor', 'waar', 'wat', 'wil', 'worden',
  'zijn', 'zoals', 'zich', 'ze', 'wordt', 'werd', 'heel', 'erg', 'daar',
  'toen', 'dan', 'maakt', 'maken', 'doet', 'doen', 'gaan', 'komt', 'komen',
  'graag', 'altijd', 'soms', 'vaak', 'wel', 'echt',
  // en
  'a', 'about', 'after', 'all', 'also', 'an', 'and', 'any', 'are', 'as', 'at',
  'be', 'been', 'but', 'by', 'can', 'for', 'from', 'had', 'has', 'have', 'he',
  'her', 'his', 'how', 'in', 'into', 'is', 'it', 'its', 'like', 'likes',
  'more', 'most', 'not', 'of', 'on', 'one', 'or', 'other', 'she', 'some',
  'such', 'than', 'that', 'the', 'their', 'them', 'then', 'there', 'these',
  'they', 'this', 'to', 'was', 'were', 'when', 'which', 'who', 'will', 'with',
  'would', 'you', 'your',
])

/** U279: the colour a memory node is drawn in. Lives here, beside the code
 *  that builds those nodes, so the canvas and the legend that explains it
 *  cannot drift apart — a colour nothing names is not styling, it is noise. */
export const MEMORY_COLOUR = '#8b6fc9'

export interface MemoryLine {
  /** Stable within one note, so nodes keep their identity across renders. */
  id: string
  /** The full sentence — for the hover label and the tooltip. */
  text: string
  /** The words that distinguish this line, most telling first. */
  keywords: string[]
  /** U280: people this line explicitly names as [[links]]. The distiller
   *  writes those for anyone who already has a profile, so a remembered
   *  relationship becomes a real edge between two people instead of a
   *  sentence that merely happens to contain a name. */
  refs: string[]
}

/** Split the stored note into the lines it is actually made of.
 *
 *  He writes "- one thing\n- another", but a hand-edited note may use "*",
 *  "•", or plain paragraphs — the Memory tab is an editable textarea, so
 *  whatever the owner leaves behind has to parse.
 */
export function splitMemory(note: string): string[] {
  return (note || '')
    .split(/\r?\n/)
    .map(l => l.replace(/^\s*[-*•·]\s*/, '').trim())
    .filter(l => l.length > 2)
}

function words(line: string): string[] {
  return line
    .toLowerCase()
    .replace(/\[\[([^\]]+)\]\]/g, '$1')       // a [[link]] is a word like any other
    .split(/[^\p{L}\p{N}]+/u)
    .filter(w => w.length >= 4 && !STOPWORDS.has(w))
}

/**
 * Turn a memory note into labelled lines plus the keywords several lines share.
 *
 * `ignore` drops words that say nothing about THIS person — their own name
 * above all, which appears in nearly every line he writes and would otherwise
 * win every ranking and label every node identically.
 */
export function memoryGraph(
  note: string, ignore: string[] = [], maxLines = 24,
): { lines: MemoryLine[]; shared: string[] } {
  const skip = new Set(ignore.flatMap(n => words(n)))
  const raw = splitMemory(note).slice(0, maxLines)

  const perLine = raw.map(text => words(text).filter(w => !skip.has(w)))

  // How many LINES a word appears in — not how often overall, so one line
  // repeating a word does not make it look like a shared theme.
  const spread = new Map<string, number>()
  for (const ws of perLine) {
    for (const w of new Set(ws)) spread.set(w, (spread.get(w) ?? 0) + 1)
  }

  const lines: MemoryLine[] = raw.map((text, i) => ({
    id: `m${i}`,
    text,
    // U280: [[jappe]] in a remembered line is a link to that person's profile.
    refs: [...text.matchAll(/\[\[([^\]]+)\]\]/g)].map(m => m[1].trim()).filter(Boolean),
    // Rank by reach first (a word tying lines together is the interesting
    // one), then by length as a plain tiebreak. Order within the line is
    // preserved for equal scores, so labels read the way the sentence does.
    keywords: [...new Set(perLine[i])]
      .sort((a, b) => (spread.get(b)! - spread.get(a)!) || (b.length - a.length))
      .slice(0, 2),
  }))

  const shared = [...spread.entries()]
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([w]) => w)

  return { lines, shared }
}

/** What a memory node says on the canvas: its keywords, or a short fallback. */
/** The sentence with its link markup removed - what a reader should see. */
export function memoryText(line: MemoryLine): string {
  return line.text.replace(/\[\[([^\]]+)\]\]/g, '$1')
}

export function memoryLabel(line: MemoryLine): string {
  if (line.keywords.length) return line.keywords.join(' · ')
  return line.text.slice(0, 28)
}
