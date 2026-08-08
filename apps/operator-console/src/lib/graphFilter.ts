// U214: narrowing the brain graph to one or more people.
//
// Pulled out of BrainGraph's canvas code so the rule is testable on its own —
// which matters, because "what disappears" is the whole point of a filter and
// getting it subtly wrong (dropping the shared skills, keeping someone else's
// facts) is invisible in a force-directed blob.

export interface GraphPerson { person_id: string; display_name: string }
export interface GraphSkill { name: string; description: string; person: string; body: string }
export interface GraphFactRow { person_id: string; key: string; value: string }

export interface GraphInput {
  people: GraphPerson[]
  skills: GraphSkill[]
  facts: GraphFactRow[]
}

/**
 * Keep only what belongs to `onlyPeople` (empty → everything unchanged).
 *
 * Skills WITHOUT a person are general — they apply to everyone, so they stay.
 * Dropping them would make the shared library vanish the moment you focus on
 * someone, which reads as data loss rather than a filter.
 */
export function filterGraph(input: GraphInput, onlyPeople: string[] = []): GraphInput {
  const only = new Set(onlyPeople.map(p => p.toLowerCase()))
  if (!only.size) return input
  const keep = (id: string) => only.has((id ?? '').toLowerCase())
  return {
    people: input.people.filter(p => keep(p.person_id)),
    skills: input.skills.filter(s => !s.person || keep(s.person)),
    facts: input.facts.filter(f => keep(f.person_id)),
  }
}
