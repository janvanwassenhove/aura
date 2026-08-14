"""The assistant brings a skill up by itself — U250.

Everything needed for this already existed. U107 could propose a rewrite, U247
gave it real evidence, U249 taught the trigger to weigh failure over
popularity. The missing piece was the smallest one: **nobody ever looked**. The
proposal waited behind a button in the console, so a skill could die at the
same step every day and the loop would never mention it.

This is the looking. It runs on the maintenance tick — already the place that
asks "how are things" every five minutes — picks at most ONE thing worth
raising, drafts it, and publishes it as a question.

Two kinds:
  * a REWRITE of a skill whose recent record shows it keeps going wrong,
  * a NEW skill for something asked repeatedly that no skill covers.

Three rules that keep this from becoming noise:
  1. One proposal at a time. A list of five is a backlog; one with a reason is
     a question the owner can answer.
  2. A cooldown per subject, so a tick every five minutes cannot raise the same
     skill twelve times an hour.
  3. Nothing is ever saved. The owner applies it through the ordinary save
     path, exactly as with every skill write since U59.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class SkillProposer:
    def __init__(self, store: Any, bus: Any, session_id: str = "default") -> None:
        self._store = store
        self._bus = bus
        self._session_id = session_id
        # subject → when it was last raised. In memory on purpose: a restart
        # re-raising a still-valid proposal is the correct behaviour, and a
        # file here would be one more thing that can rot.
        self._last_raised: dict[str, float] = {}

    async def review(self, *, now: float | None = None) -> dict | None:
        """Look once. Returns the proposal raised, or None when there is
        nothing worth the owner's attention (which is most ticks)."""
        from orchestrator import skill_review

        try:
            pick = skill_review.pick(
                self._store, now=now, last_raised=self._last_raised)
        except Exception as exc:  # noqa: BLE001 — the maintainer must not need maintenance
            logger.debug("skill review failed: %s", exc)
            return None
        if pick is None:
            return None

        proposal = (await self._draft_rewrite(pick) if pick.kind == "rewrite"
                    else await self._draft_new(pick))
        if proposal is None:
            # Mark it anyway: a subject that produced nothing usable should not
            # be re-tried every five minutes either.
            self._last_raised[f"{pick.kind}:{pick.name}"] = now or time.time()
            return None

        self._last_raised[f"{pick.kind}:{pick.name}"] = now or time.time()
        await self._publish(proposal)
        logger.info("raised a %s proposal for %r (%s)",
                    pick.kind, pick.name, pick.reason)
        return proposal

    # -- drafting -------------------------------------------------------

    async def _draft_rewrite(self, pick) -> dict | None:
        from orchestrator.config import model_for_role
        from orchestrator.llm import openai_chat
        from orchestrator.skill_optimizer import propose_optimization

        result = await propose_optimization(
            self._store, pick.name, openai_chat, model=model_for_role("agent"))
        if "error" in result or not result.get("changed"):
            # "Nothing to change" is a fine answer and not worth interrupting
            # for — but it HAS consumed the evidence, so reset the counter or
            # the same skill queues up again on the next tick.
            if "error" not in result:
                try:
                    self._store.mark_optimized(pick.name)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("mark_optimized failed: %s", exc)
            return None
        return {
            "kind": "rewrite", "skill": pick.name, "reason": pick.reason,
            "rationale": result.get("rationale", ""),
            "current_body": result.get("current_body", ""),
            "proposed_body": result.get("proposed_body", ""),
        }

    async def _draft_new(self, pick) -> dict | None:
        from orchestrator.config import model_for_role
        from orchestrator.llm import openai_chat
        from orchestrator.skill_optimizer import propose_new_skill
        from orchestrator.tool_schemas import LADDER_NOTE

        result = await propose_new_skill(
            self._store, list(pick.examples), openai_chat,
            tools=LADDER_NOTE, model=model_for_role("agent"))
        if "error" in result or not result.get("worth_adding"):
            return None
        return {
            "kind": "new", "skill": result["name"], "reason": pick.reason,
            "rationale": result.get("rationale", ""),
            "description": result.get("description", ""),
            "triggers": result.get("triggers", []),
            "current_body": "",
            "proposed_body": result.get("body", ""),
        }

    async def _publish(self, proposal: dict) -> None:
        from shared_schemas.events.system import SkillProposalRaised

        await self._bus.publish(SkillProposalRaised(
            session_id=self._session_id, **proposal))
