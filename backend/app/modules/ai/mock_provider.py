from typing import List
from app.modules.ai.provider import AIProvider
from app.modules.ai.schemas import (
    DealGuidanceRequest,
    DealGuidanceResponse,
    LeadPrioritizationRequest,
    LeadSummaryRequest,
    MessageDraftRequest,
    MessageDraftResponse,
    NextActionRequest,
    AINextActionResponse,
    AIPriorityResponse,
    AISummaryResponse,
)


class MockAIProvider(AIProvider):
    """Default zero-cost AI provider that produces realistic, context-aware structured outputs."""

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_available(self) -> bool:
        return True

    async def generate_summary(self, request: LeadSummaryRequest) -> AISummaryResponse:
        contact = request.contact_name or "The customer"
        company_str = f" at {request.company_name}" if request.company_name else ""
        stage = request.stage.capitalize() if request.stage else "New"
        val_str = f"${request.estimated_value:,.2f}" if request.estimated_value > 0 else "an unspecified budget"

        # Check activities for recent context
        act_count = len(request.activities)
        recent_desc = ""
        if act_count > 0:
            last_act = request.activities[0]
            recent_desc = f" Recent interaction ({last_act.get('type', 'activity')}): {last_act.get('title', 'Discussion logged')}."

        summary_text = (
            f"{contact}{company_str} is currently in the {stage} stage with an estimated opportunity of {val_str}."
            f"{recent_desc} Customer has demonstrated active interest and is awaiting the next engagement milestone."
        )

        key_points = [
            f"Stage: {stage}",
            f"Opportunity Value: {val_str}",
            f"Recorded Interactions: {act_count} touchpoint(s)",
        ]
        if request.notes:
            key_points.append(f"Notes context: {request.notes[:100]}...")

        sentiment = "positive" if stage in ["Qualified", "Interested", "Proposal", "Negotiation", "Won"] else "neutral"

        return AISummaryResponse(
            summary=summary_text,
            sentiment=sentiment,
            key_points=key_points,
            confidence=0.92,
            provider="mock-ai-engine",
        )

    async def prioritize_lead(self, request: LeadPrioritizationRequest) -> AIPriorityResponse:
        score = 50
        reasons: List[str] = []

        # Scoring heuristics reflecting real CRM dynamics
        if request.estimated_value >= 10000:
            score += 25
            reasons.append(f"High deal value (${request.estimated_value:,.2f}) represents significant revenue impact.")
        elif request.estimated_value >= 3000:
            score += 15
            reasons.append(f"Solid deal value (${request.estimated_value:,.2f}) above average deal size.")

        if request.stage.upper() in ["PROPOSAL", "NEGOTIATION"]:
            score += 20
            reasons.append(f"In late-stage sales cycle ({request.stage.upper()}); immediate closing opportunity.")
        elif request.stage.upper() == "QUALIFIED":
            score += 10
            reasons.append("Lead is qualified with verified business need.")

        if request.overdue_tasks_count > 0:
            score += 15
            reasons.append(f"{request.overdue_tasks_count} overdue follow-up task(s) require urgent intervention.")

        if request.days_since_last_contact > 5:
            score += 10
            reasons.append(f"No recorded touchpoint for {request.days_since_last_contact} days; risk of lead going cold.")

        score = min(score, 100)

        if score >= 80:
            level = "URGENT" if request.overdue_tasks_count > 0 else "HIGH"
            focus = "Immediate outreach to advance proposal or prevent lead decay."
        elif score >= 60:
            level = "MEDIUM"
            focus = "Follow up with product demo or tailored collateral."
        else:
            level = "LOW"
            focus = "Nurture with automated sequence or informational check-in."

        return AIPriorityResponse(
            priority_level=level,
            priority_score=score,
            reasons=reasons or ["Standard inbound lead in early qualification."],
            suggested_focus=focus,
            confidence=0.88,
            provider="mock-ai-engine",
        )

    async def recommend_next_action(self, request: NextActionRequest) -> AINextActionResponse:
        stage = (request.stage or "").upper()
        contact = request.contact_name or "the lead"

        if stage == "NEW":
            action = f"Initiate discovery call with {contact} within 2 business hours."
            rationale = "Rapid initial contact increases lead qualification rates by over 300%."
            urgency = "immediate"
            task_title = f"First discovery call with {contact}"
            due_days = 0
        elif stage == "CONTACTED":
            action = f"Send introductory overview and schedule qualification demo."
            rationale = "Move lead from basic contact to structured needs assessment."
            urgency = "today"
            task_title = f"Qualify requirements and schedule demo for {contact}"
            due_days = 1
        elif stage == "PROPOSAL":
            action = f"Follow up on proposal terms and review pricing breakdown with {contact}."
            rationale = "Active proposals without follow-up within 72 hours stall in 45% of cases."
            urgency = "today"
            task_title = f"Follow up on proposal with {contact}"
            due_days = 1
        elif stage == "NEGOTIATION":
            action = f"Send revised agreement or final closing contract."
            rationale = "Customer is in final decision phase; address any remaining objections to secure signature."
            urgency = "immediate"
            task_title = f"Finalize contract details with {contact}"
            due_days = 0
        else:
            action = f"Check in on upcoming milestones and maintain relationship."
            rationale = "Consistent cadence keeps brand top-of-mind."
            urgency = "this_week"
            task_title = f"Touchpoint check-in with {contact}"
            due_days = 3

        return AINextActionResponse(
            recommended_action=action,
            rationale=rationale,
            urgency=urgency,
            suggested_task_title=task_title,
            suggested_due_days=due_days,
            confidence=0.94,
            provider="mock-ai-engine",
        )

    async def draft_message(self, request: MessageDraftRequest) -> MessageDraftResponse:
        channel = request.channel.lower()
        recipient = request.recipient_name
        company = f" at {request.company_name}" if request.company_name else ""
        topic = request.last_discussion_topic or "our recent conversation"
        val_str = f" (${request.proposal_value:,.2f})" if request.proposal_value else ""

        if channel == "whatsapp":
            body = (
                f"Hi {recipient}, hope you're having a great week! Just following up regarding {topic}. "
                f"Let me know if you have any questions on the details we shared{val_str} or if you'd like a quick 5-min call to finalize things."
            )
            subject = None
            cta = "Reply on WhatsApp or confirm a convenient call time."
        else:
            # Email
            subject = f"Following up on our discussion regarding {topic} - NexusCRM"
            body = (
                f"Hi {recipient},\n\n"
                f"I hope you are doing well.\n\n"
                f"I'm reaching out to follow up on {topic}{company}. Based on our previous discussion, "
                f"we've prepared the necessary details{val_str} to ensure a seamless implementation tailored to your goals.\n\n"
                f"Would you be available for a brief 15-minute sync tomorrow or Thursday to review any remaining questions?\n\n"
                f"Looking forward to hearing from you.\n\n"
                f"Best regards,\nSales Operations Team"
            )
            cta = "Book a 15-minute review session."

        return MessageDraftResponse(
            channel=channel,
            subject=subject,
            body=body,
            call_to_action=cta,
            confidence=0.95,
            provider="mock-ai-engine",
        )

    async def provide_deal_guidance(self, request: DealGuidanceRequest) -> DealGuidanceResponse:
        days = request.days_in_current_stage
        health = "on_track"
        win_prob = 70
        risks: List[str] = []
        tactics: List[str] = []

        if days > 14:
            health = "stalled"
            win_prob = 35
            risks.append(f"Deal has remained in '{request.stage}' for {days} days without progression.")
            tactics.append("Executive check-in or re-engagement offer to unblock decision makers.")
        elif days > 7:
            health = "at_risk"
            win_prob = 55
            risks.append("Momentum is slowing down compared to target sales cycle velocity.")
            tactics.append("Schedule a specific objection-handling call with primary stakeholders.")
        else:
            win_prob = 80
            tactics.append("Maintain active communication cadence to close within expected timeframe.")

        return DealGuidanceResponse(
            stage_health=health,
            win_probability_estimate=win_prob,
            risk_factors=risks or ["No critical risk factors detected."],
            recommended_tactics=tactics,
            confidence=0.90,
            provider="mock-ai-engine",
        )
