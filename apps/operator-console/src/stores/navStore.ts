import { defineStore } from 'pinia'
import { ref } from 'vue'

/** D2: one navigation system. A collapsible labelled rail switches between
 * these views — no more title-bar icon soup + five full-screen modals.
 * `graph` and `wizard` are reachable but not rail items. */
export type View =
  | 'talk' | 'people' | 'skills' | 'robot' | 'present'
  | 'activity' | 'modes' | 'settings' | 'about' | 'graph'

export const useNavStore = defineStore('nav', () => {
  const view = ref<View>('talk')

  function go(v: View): void { view.value = v }

  /** U68: cross-panel navigation for [[wikilinks]] — a click on [[jan]] in a
   * skill opens that person; a click on [[skill-name]] opens Skills with that
   * skill in the editor. */
  const knowledgeRequest = ref<{ personId: string; ts: number } | null>(null)
  const skillsRequest = ref<{ skillName?: string; ts: number } | null>(null)

  function openPerson(personId: string): void {
    knowledgeRequest.value = { personId, ts: Date.now() }
    view.value = 'people'
  }

  function openSkills(skillName?: string): void {
    skillsRequest.value = { skillName, ts: Date.now() }
    view.value = 'skills'
  }

  return { view, go, knowledgeRequest, skillsRequest, openPerson, openSkills }
})
