/** D2 character archetypes — personality + look + motion, as one choice.
 *
 * Original archetypes: genre nods, not copies of any specific robot. Each one
 * carries its own idle/speaking/moving SVG (SMIL animations, so no JS per
 * frame), a voice line, and traits. Ported verbatim from the design prototype;
 * colours reference the theme tokens so both themes work.
 *
 * The art is generated as an SVG string and rendered with v-html — content is
 * entirely local and static, never user input.
 */

export type CharacterAct = 'idle' | 'speak' | 'move'

export interface Archetype {
  name: string
  tag: string
  hue: string
  tagline: string
  sample: string
  traits: string
  hint: string
  /** The signature move: a REAL robot motion with the speed and amplitude
   *  that make it read as this character. "Try a move" used to send the
   *  same generic gesture for all ten — the traits said "reluctant motion"
   *  and the robot moved like everyone else. */
  move: { id: string; speed: number; amplitude: number; why: string }
  art: (px: number, act?: CharacterAct) => string
}

const SVG = (px: number, body: string, anim: boolean) =>
  `<svg viewBox="0 0 64 64" style="width:${px}px;height:${px}px;${anim ? 'animation:breathe 4.6s ease-in-out infinite;' : ''}" fill="none">${body}</svg>`

const A = (attr: string, values: string, dur: string, extra = '') =>
  `<animate attributeName="${attr}" values="${values}" dur="${dur}" repeatCount="indefinite" ${extra}/>`
const AT = (type: string, values: string, dur: string) =>
  `<animateTransform attributeName="transform" type="${type}" values="${values}" dur="${dur}" repeatCount="indefinite" />`

/** Voice bars: only while speaking, so silence looks like silence. */
const VOICE = (act: CharacterAct, hue: string, y = 58) => act !== 'speak' ? '' :
  [0, 1, 2, 3, 4].map(i =>
    `<rect x="${23 + i * 4}" y="${y - 3}" width="2.4" height="3" rx="1.2" fill="${hue}">` +
    A('height', i % 2 ? '3;9;4;3' : '3;6;10;3', `${0.5 + i * 0.11}s`) +
    A('y', i % 2 ? `${y - 3};${y - 9};${y - 4};${y - 3}` : `${y - 3};${y - 6};${y - 10};${y - 3}`, `${0.5 + i * 0.11}s`) +
    '</rect>').join('')

export const CHARACTERS: Record<string, Archetype> = {
  scout: {
    name: 'Richie', tag: 'Scout', hue: '#1f6f46',
    tagline: 'Cheerful sidekick with antennas. The default.',
    sample: '“Morning! Three meetings today — the 11:00 still has no agenda. Want me to poke Priya about it?”',
    traits: 'warm voice · chatty · bouncy motion',
    hint: 'friendly, a bit eager, explains what it is doing',
    move: { id: 'wave', speed: 1.15, amplitude: 0.8, why: 'bouncy — a quick, big wave' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('rotate', '-4 32 40;4 32 40;-4 32 40', '1.1s') : ''}
      <g stroke="var(--ink)" stroke-width="1.9" stroke-linecap="round"><path d="M18 26 L13 6"></path><path d="M46 26 L52 8"></path></g>
      <circle cx="13" cy="5" r="2.4" fill="#1f6f46">${act !== 'idle' ? A('r', '2.4;3.6;2.4', '0.9s') : ''}</circle>
      <circle cx="52.4" cy="7" r="2.4" fill="#1f6f46">${act !== 'idle' ? A('r', '2.4;3.6;2.4', '0.9s', 'begin="0.3s"') : ''}</circle>
      <rect x="8" y="21" width="48" height="31" rx="14" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.3"></rect>
      <circle cx="22.5" cy="36" r="8.4" fill="var(--ink)">${A('ry', '8.4;8.4;1;8.4', '5s')}</circle>
      <circle cx="41.5" cy="36" r="8.4" fill="var(--ink)">${A('ry', '8.4;8.4;1;8.4', '5s')}</circle>
      <circle cx="25.6" cy="32.6" r="2.4" fill="var(--surface)"></circle><circle cx="44.6" cy="32.6" r="2.4" fill="var(--surface)"></circle>
    </g>${VOICE(act, '#1f6f46')}`, act === 'idle'),
  },
  sentinel: {
    name: 'Richie', tag: 'Sentinel', hue: '#c0392b',
    tagline: 'Dashboard co-pilot. Clipped, factual, always scanning.',
    sample: '“Three meetings. The 11:00 has no agenda. Recommend a nudge.”',
    traits: 'flat voice · terse · minimal motion',
    hint: 'answers in one line, no small talk, states confidence',
    move: { id: 'nod', speed: 0.85, amplitude: 0.35, why: 'minimal — one small nod, nothing more' },
    art: (px, act = 'idle') => SVG(px, `<rect x="6" y="20" width="52" height="24" rx="6" fill="#1a1a1d" stroke="var(--ink)" stroke-width="2.2"></rect>
      <rect x="12" y="30" width="40" height="4" rx="2" fill="#3a1512"></rect>
      ${act === 'speak'
        ? `<rect x="12" y="30" width="40" height="4" rx="2" fill="#e0392b">${A('opacity', '0.35;1;0.5;1;0.35', '0.7s')}</rect>`
        : `<rect x="20" y="30" width="16" height="4" rx="2" fill="#e0392b">${A('x', '12;36;12', act === 'move' ? '0.9s' : '2.6s')}</rect>`}
      <path d="M18 44v6M46 44v6" stroke="var(--ink)" stroke-width="2.2" stroke-linecap="round"></path>${VOICE(act, '#e0392b', 60)}`, false),
  },
  slab: {
    name: 'Richie', tag: 'Slab', hue: '#5a6572',
    tagline: 'Deadpan monolith. Dry jokes, dialled to taste.',
    sample: '“Three meetings. Two could have been an email. Humour setting: 70%.”',
    traits: 'low voice · dry humour · deliberate motion',
    hint: 'humour and honesty are sliders you set yourself',
    move: { id: 'look_around', speed: 0.7, amplitude: 0.6, why: 'deliberate — a slow, full look around' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('translate', '0 0;3 -2;0 0;-3 -2;0 0', '1.6s') : ''}
      <rect x="20" y="6" width="24" height="18" rx="3" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.2">${act === 'move' ? AT('translate', '0 0;5 0;0 0', '1.6s') : ''}</rect>
      <rect x="20" y="24" width="24" height="16" rx="3" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.2"></rect>
      <rect x="20" y="40" width="24" height="18" rx="3" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.2">${act === 'move' ? AT('translate', '0 0;-5 0;0 0', '1.6s') : ''}</rect>
      <rect x="26" y="12" width="12" height="6" rx="1.5" fill="#5a6572">${act === 'speak' ? A('opacity', '0.4;1;0.4', '0.55s') : ''}</rect>
      <path d="M26 46h12" stroke="#5a6572" stroke-width="2.4" stroke-linecap="round"></path>
    </g>${VOICE(act, '#5a6572', 62)}`, act === 'idle'),
  },
  mender: {
    name: 'Richie', tag: 'Mender', hue: '#3d7fb8',
    tagline: 'Soft-spoken carer. Checks in, never rushes you.',
    sample: '“Three meetings today, and a long stretch in the middle. Shall I hold twenty minutes for a break?”',
    traits: 'gentle voice · patient · slow motion',
    hint: 'asks how you are, keeps answers calm and short',
    move: { id: 'nod', speed: 0.6, amplitude: 0.5, why: 'slow, patient — an unhurried nod' },
    art: (px, act = 'idle') => SVG(px, `<ellipse cx="32" cy="34" rx="24" ry="21" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.4">${act !== 'idle' ? A('ry', '21;22.4;21', act === 'move' ? '2s' : '3.2s') + A('rx', '24;23;24', act === 'move' ? '2s' : '3.2s') : ''}</ellipse>
      <circle cx="23" cy="32" r="3.4" fill="var(--ink)">${A('r', '3.4;3.4;0.6;3.4', '4.5s')}${act === 'speak' ? A('cy', '32;30.6;32', '0.9s') : ''}</circle>
      <circle cx="41" cy="32" r="3.4" fill="var(--ink)">${A('r', '3.4;3.4;0.6;3.4', '4.5s')}${act === 'speak' ? A('cy', '32;30.6;32', '0.9s') : ''}</circle>
      <path d="M26.4 32h11.2" stroke="var(--ink)" stroke-width="2.2" stroke-linecap="round"></path>${VOICE(act, '#3d7fb8', 60)}`, act === 'idle'),
  },
  astro: {
    name: 'Richie', tag: 'Astro', hue: '#2f7fd0',
    tagline: 'Chirps and whistles. More expressive than talkative.',
    sample: '“▪▫ chirp — whistle ▫▪”  ·  subtitle: three meetings, one missing an agenda.',
    traits: 'beeps + subtitles · playful · fast motion',
    hint: 'answers in sounds and gestures, text in the transcript',
    move: { id: 'bop', speed: 1.4, amplitude: 0.7, why: 'fast, playful — a quick bop' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('rotate', '-7 32 44;7 32 44;-7 32 44', '1.3s') : ''}
      <g>${act !== 'idle' ? AT('rotate', '-12 32 30;12 32 30;-12 32 30', act === 'speak' ? '1.8s' : '1.1s') : ''}
        <path d="M14 30a18 18 0 0 1 36 0z" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.2"></path>
        <circle cx="32" cy="22" r="4.5" fill="#2f7fd0" stroke="var(--ink)" stroke-width="1.6">${act === 'speak' ? A('opacity', '1;0.3;1;0.6;1', '0.6s') : ''}</circle>
      </g>
      <rect x="14" y="30" width="36" height="26" rx="4" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.2"></rect>
      <path d="M20 38h8M20 46h20" stroke="var(--ink)" stroke-width="1.8" stroke-linecap="round"></path>
      <circle cx="42" cy="38" r="3" fill="#2f7fd0">${act !== 'idle' ? A('opacity', '0.3;1;0.3', '0.45s') : ''}</circle>
    </g>${act === 'speak' ? `<g fill="#2f7fd0"><circle cx="52" cy="20" r="1.8">${A('cy', '20;10', '1.2s')}${A('opacity', '1;0', '1.2s')}</circle><circle cx="57" cy="24" r="1.4">${A('cy', '24;14', '1.2s', 'begin="0.4s"')}${A('opacity', '1;0', '1.2s', 'begin="0.4s"')}</circle></g>` : ''}`, act === 'idle'),
  },
  grump: {
    name: 'Richie', tag: 'Grump', hue: '#7a6a8f',
    tagline: 'Does everything, enjoys nothing. Complains, then complies.',
    sample: '“Three meetings. None of them will change anything. I have prepped all three anyway.”',
    traits: 'flat voice · pessimistic · reluctant motion',
    hint: 'sighs first, still does the job correctly',
    move: { id: 'shake', speed: 0.75, amplitude: 0.4, why: 'reluctant — a small, slow head-shake, then he complies' },
    art: (px, act = 'idle') => SVG(px, `<g>${act !== 'idle' ? AT('translate', '0 0;0 2.5;0 0', act === 'move' ? '2.4s' : '3.4s') : ''}
      <rect x="10" y="18" width="44" height="34" rx="16" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.3"></rect>
      <circle cx="23" cy="34" r="7" fill="var(--ink)"></circle><circle cx="41" cy="34" r="7" fill="var(--ink)"></circle>
      <path d="M14 27q9 -5 18 0M32 27q9 -5 18 0" stroke="var(--ink)" stroke-width="2.6" stroke-linecap="round">${act === 'speak' ? A('d', 'M14 27q9 -5 18 0M32 27q9 -5 18 0;M14 29q9 -5 18 0M32 29q9 -5 18 0;M14 27q9 -5 18 0M32 27q9 -5 18 0', '2.2s') : ''}</path>
      <path d="M24 46q8 -4 16 0" stroke="#7a6a8f" stroke-width="2.2" stroke-linecap="round"></path>
    </g>${VOICE(act, '#7a6a8f', 60)}`, false),
  },
  halo: {
    name: 'Richie', tag: 'Halo', hue: '#00b3c8',
    tagline: 'Futuristic hologram. Precise, cool, slightly ahead of you.',
    sample: '“Three meetings. Agenda missing for 11:00 — drafting a request now.”',
    traits: 'synth voice · precise · floating motion',
    hint: 'anticipates the next step and states it',
    move: { id: 'sway', speed: 0.8, amplitude: 0.55, why: 'floating — a smooth, even sway' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('translate', '0 0;0 -3;0 0', '2s') : ''}
      <ellipse cx="32" cy="56" rx="16" ry="3" fill="#00b3c8" opacity="0.25">${act !== 'idle' ? A('rx', '16;11;16', '2s') : ''}</ellipse>
      <path d="M20 14h24l6 10-6 20H20l-6-20z" fill="var(--surface-2)" stroke="#00b3c8" stroke-width="2.2"></path>
      <path d="M22 26h20" stroke="#00b3c8" stroke-width="3" stroke-linecap="round">${act === 'speak' ? A('opacity', '1;0.25;1', '0.5s') : ''}</path>
      <path d="M25 34h14" stroke="#00b3c8" stroke-width="1.6" stroke-linecap="round" opacity="0.6"></path>
      ${act !== 'idle' ? `<path d="M14 20h-6M56 20h6M14 38h-6M56 38h6" stroke="#00b3c8" stroke-width="1.6" stroke-linecap="round">${A('opacity', '0.2;1;0.2', '1.4s')}</path>` : ''}
    </g>${VOICE(act, '#00b3c8', 60)}`, act === 'idle'),
  },
  buddy: {
    name: 'Richie', tag: 'Buddy', hue: '#e07b39',
    tagline: 'Kids companion. Big eyes, small words, endless patience.',
    sample: '“You have school at nine! Want me to tell you a dinosaur fact while you eat?”',
    traits: 'bright voice · simple words · bouncy motion',
    hint: 'age-appropriate answers, never scary, always encouraging',
    move: { id: 'dance', speed: 1.2, amplitude: 0.8, why: 'bouncy — the whole dance, big and bright' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('translate', '0 0;0 -4;0 1;0 0', '0.8s') : ''}
      <circle cx="32" cy="34" r="23" fill="#ffd9b8" stroke="var(--ink)" stroke-width="2.4"></circle>
      <circle cx="24" cy="31" r="6.5" fill="var(--ink)">${A('ry', '6.5;6.5;0.8;6.5', '3.6s')}</circle>
      <circle cx="40" cy="31" r="6.5" fill="var(--ink)">${A('ry', '6.5;6.5;0.8;6.5', '3.6s')}</circle>
      <circle cx="26" cy="28.6" r="2.2" fill="#fff"></circle><circle cx="42" cy="28.6" r="2.2" fill="#fff"></circle>
      <path d="M25 43q7 ${act === 'speak' ? 8 : 5} 14 0" stroke="var(--ink)" stroke-width="2.4" stroke-linecap="round" fill="none">${act === 'speak' ? A('d', 'M25 43q7 8 14 0;M25 43q7 3 14 0;M25 43q7 8 14 0', '0.6s') : ''}</path>
      <circle cx="12" cy="34" r="4" fill="#e07b39"></circle><circle cx="52" cy="34" r="4" fill="#e07b39"></circle>
    </g>${VOICE(act, '#e07b39', 62)}`, act === 'idle'),
  },
  host: {
    name: 'Richie', tag: 'Host', hue: '#6d4fa1',
    tagline: 'Stage presenter. Projects, times a pause, works a room.',
    sample: '“Three meetings today — and the eleven o’clock, ladies and gentlemen, still has no agenda.”',
    traits: 'projected voice · theatrical · broad gestures',
    hint: 'built for an audience, not a desk',
    move: { id: 'bow', speed: 1.0, amplitude: 1.0, why: 'theatrical — the full bow, arms wide' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('rotate', '-6 32 48;6 32 48;-6 32 48', '1.5s') : ''}
      <rect x="12" y="18" width="40" height="28" rx="8" fill="var(--surface-2)" stroke="var(--ink)" stroke-width="2.3"></rect>
      <circle cx="24" cy="31" r="5.4" fill="var(--ink)"></circle><circle cx="40" cy="31" r="5.4" fill="var(--ink)"></circle>
      <path d="M22 40h20" stroke="#6d4fa1" stroke-width="2.6" stroke-linecap="round">${act === 'speak' ? A('d', 'M22 40h20;M26 40h12;M22 40h20', '0.5s') : ''}</path>
      <path d="M20 18l-6-8M44 18l6-8" stroke="var(--ink)" stroke-width="2" stroke-linecap="round"></path>
      <path d="M18 50q14 8 28 0" stroke="#6d4fa1" stroke-width="2.4" stroke-linecap="round" fill="none"></path>
      ${act === 'speak' ? `<path d="M54 26q6 6 0 12" stroke="#6d4fa1" stroke-width="1.8" stroke-linecap="round" fill="none">${A('opacity', '0.2;1;0.2', '0.8s')}</path><path d="M10 26q-6 6 0 12" stroke="#6d4fa1" stroke-width="1.8" stroke-linecap="round" fill="none">${A('opacity', '0.2;1;0.2', '0.8s')}</path>` : ''}
    </g>`, act === 'idle'),
  },
  orb: {
    name: 'Richie', tag: 'Orb', hue: '#4aa3c7',
    tagline: 'Smooth, curious, almost silent. Watches before it speaks.',
    sample: '“Three today. One needs an agenda.”',
    traits: 'clear voice · sparse words · gliding motion',
    hint: 'says the minimum, shows the rest on screen',
    move: { id: 'look_around', speed: 0.65, amplitude: 0.45, why: 'gliding — a slow, sparse turn' },
    art: (px, act = 'idle') => SVG(px, `<g>${act === 'move' ? AT('rotate', '-6 32 44;6 32 44;-6 32 44', '2.2s') : ''}
      <ellipse cx="32" cy="32" rx="21" ry="25" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.3"></ellipse>
      <path d="M18 27q14 -8 28 0v6q-14 6 -28 0z" fill="#1a2430"></path>
      <path d="M24 30l4 3M40 30l-4 3" stroke="#4aa3c7" stroke-width="2.4" stroke-linecap="round">${act === 'speak' ? A('opacity', '1;0.35;1', '0.8s') : ''}</path>
      ${act !== 'idle' ? `<rect x="16" y="27" width="7" height="10" fill="#4aa3c7" opacity="0.25">${A('x', '16;41;16', '2.8s')}</rect>` : ''}
    </g>${VOICE(act, '#4aa3c7', 62)}`, act === 'idle'),
  },
}

export const DEFAULT_CHARACTER = 'scout'

export function archetype(id: string | null | undefined): Archetype {
  return CHARACTERS[id ?? DEFAULT_CHARACTER] ?? CHARACTERS[DEFAULT_CHARACTER]
}
