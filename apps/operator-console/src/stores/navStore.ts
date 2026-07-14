import { defineStore } from 'pinia'
import { ref } from 'vue'

/** U68: cross-panel navigation for [[wikilinks]] — a click on [[jan]] in a
 * skill opens that person in the Knowledge panel; a click on [[skill-name]]
 * in a profile opens the Skills tab with that skill in the editor. */
export const useNavStore = defineStore('nav', () => {
  const knowledgeRequest = ref<{ personId: string; ts: number } | null>(null)
  const skillsRequest = ref<{ skillName?: string; ts: number } | null>(null)

  function openPerson(personId: string): void {
    knowledgeRequest.value = { personId, ts: Date.now() }
  }

  function openSkills(skillName?: string): void {
    skillsRequest.value = { skillName, ts: Date.now() }
  }

  return { knowledgeRequest, skillsRequest, openPerson, openSkills }
})
