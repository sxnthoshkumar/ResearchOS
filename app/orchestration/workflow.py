"""
Central Multi-Agent Research Orchestrator.
Manages the lifecycle of autonomous research runs, enforces the finite state machine,
coordinates the five specialized agents, manages bounded retries, and publishes real-time events.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Dict, List, Optional, Set

from app.agents.analyst import AnalysisAgent
from app.agents.fact_checker import FactCheckingAgent
from app.agents.planner import PlannerAgent, ResearchPlan
from app.agents.report_writer import ReportWriterAgent
from app.agents.researcher import ResearchAgent
from app.config import settings
from app.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    ReportRepository,
    RunRepository,
    SourceRepository,
    TaskRepository,
)
from app.llm import get_llm_provider
from app.orchestration.events import broadcaster
from app.orchestration.state import WorkflowState, validate_transition

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """Controls the end-to-end execution of the five-agent collaborative research pipeline."""

    def __init__(self):
        self._cancelled_runs: Set[str] = set()

    def cancel_run(self, run_id: str) -> bool:
        """Flags a run for clean cancellation during execution."""
        run = RunRepository.get(run_id)
        if not run:
            return False
        if run["status"] in (WorkflowState.COMPLETED.value, WorkflowState.FAILED.value, WorkflowState.CANCELLED.value):
            return False

        self._cancelled_runs.add(run_id)
        RunRepository.update_status(run_id, WorkflowState.CANCELLED.value, error_message="Cancelled by user action.")
        asyncio.create_task(
            broadcaster.broadcast(
                run_id,
                "RUN_CANCELLED",
                {"run_id": run_id, "message": "Research execution cancelled by user."},
            )
        )
        return True

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled_runs

    async def execute_run(self, run_id: str) -> Dict[str, Any]:
        """Main orchestrator loop executing the five specialized agents sequentially."""
        run = RunRepository.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} does not exist.")

        question = run["question"]
        raw_mode = (run.get("provider_mode") or settings.LLM_PROVIDER).lower()
        is_demo_run = (raw_mode == "demo")
        is_demo_sources = is_demo_run
        force_demo_llm = is_demo_run

        search_providers = run["search_providers"].split(",") if run.get("search_providers") else ["openalex", "arxiv"]
        max_sources = run.get("max_sources", 10)
        max_retries = run.get("max_retries", 2)

        # Resolve provider: 'demo', 'ollama', or 'openai'
        provider_name = "demo" if force_demo_llm else ("ollama" if raw_mode in ("ollama", "live") else raw_mode)
        llm = get_llm_provider(force_demo=force_demo_llm, provider_name=provider_name)

        planner = PlannerAgent(llm)
        researcher = ResearchAgent(llm_provider=llm)
        analyst = AnalysisAgent(llm)
        fact_checker = FactCheckingAgent(llm)
        report_writer = ReportWriterAgent(llm)

        current_state = WorkflowState.CREATED

        try:
            # -------------------------------------------------------------
            # Stage 1: PLANNING
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.PLANNING)
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "agent": "planner", "message": "Planner Agent decomposing research question..."},
            )

            task_plan = TaskRepository.create(run_id, "planner", "Decompose Question & Create Research Plan", {"question": question})
            try:
                plan = await planner.create_plan(question)
                TaskRepository.finish(task_plan["id"], "COMPLETED", plan.model_dump())
            except Exception as e:
                TaskRepository.finish(task_plan["id"], "FAILED", error_message=str(e))
                raise

            # -------------------------------------------------------------
            # Stage 2: RESEARCHING (Initial Literature Harvest)
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.RESEARCHING)
            research_msg = (
                f"Research Agent querying live scholarly repositories ({', '.join(search_providers)})..."
                if not is_demo_sources
                else "Research Agent generating deterministic benchmark demonstration data..."
            )
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "agent": "researcher", "message": research_msg},
            )

            task_res = TaskRepository.create(run_id, "researcher", "Harvest Scholarly Sources & Extract Evidence", {"plan_id": plan.plan_id})
            try:
                harvest_res = await researcher.execute_plan(
                    run_id=run_id,
                    plan=plan,
                    search_providers=search_providers,
                    max_sources=max_sources,
                    is_demo=is_demo_sources,
                )
                TaskRepository.finish(task_res["id"], "COMPLETED", harvest_res.model_dump())
            except Exception as e:
                TaskRepository.finish(task_res["id"], "FAILED", error_message=str(e))
                raise

            # -------------------------------------------------------------
            # Stage 3: ANALYZING (Passage Synthesis & Claim Extraction)
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.ANALYZING)
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "agent": "analyst", "message": "Analysis Agent extracting atomic factual claims..."},
            )

            task_ana = TaskRepository.create(run_id, "analyst", "Extract Atomic Claims Linked to Evidence", {"run_id": run_id})
            try:
                analysis_res = await analyst.analyze(
                    run_id=run_id,
                    research_question=question,
                    subquestions=[sq.model_dump() for sq in plan.subquestions],
                )
                TaskRepository.finish(task_ana["id"], "COMPLETED", analysis_res.model_dump())
            except Exception as e:
                TaskRepository.finish(task_ana["id"], "FAILED", error_message=str(e))
                raise

            # -------------------------------------------------------------
            # Stage 4: VERIFYING (Adversarial Claim Fact-Checking)
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.VERIFYING)
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "agent": "fact_checker", "message": "Fact-Checking Agent auditing evidence grounds..."},
            )

            retries_remaining = max_retries - run.get("retry_count", 0)
            task_chk = TaskRepository.create(run_id, "fact_checker", "Audit Claims Against Stored Evidence", {"claims_count": analysis_res.total_claims})
            try:
                verification_res = await fact_checker.verify_claims(run_id=run_id, retry_budget_remaining=retries_remaining)
                TaskRepository.finish(task_chk["id"], "COMPLETED", verification_res.model_dump())
            except Exception as e:
                TaskRepository.finish(task_chk["id"], "FAILED", error_message=str(e))
                raise

            # -------------------------------------------------------------
            # Stage 4b: Targeted Retries if warranted
            # -------------------------------------------------------------
            if verification_res.needs_retry and retries_remaining > 0:
                self._check_cancellation(run_id)
                current_state = self._transition(run_id, current_state, WorkflowState.RETRYING)
                retry_num = RunRepository.increment_retry(run_id)
                await broadcaster.broadcast(
                    run_id,
                    "STATE_CHANGED",
                    {"state": current_state.value, "message": f"Evidence sufficiency gate triggered: Targeted retry attempt #{retry_num}."},
                )

                # Retry targeted search for deficient subquestions
                current_state = self._transition(run_id, current_state, WorkflowState.RESEARCHING)
                for subq_id in verification_res.retry_subquestions[:2]:
                    target_query = f"{question} {subq_id}"
                    await researcher.pipeline.execute_search(
                        run_id=run_id,
                        query=target_query,
                        subquestion_id=subq_id,
                        providers=search_providers,
                        max_sources_per_query=2,
                        is_demo=is_demo_sources,
                    )

                # Re-verify claims
                current_state = self._transition(run_id, current_state, WorkflowState.ANALYZING)
                await analyst.analyze(run_id=run_id, research_question=question)
                current_state = self._transition(run_id, current_state, WorkflowState.VERIFYING)
                verification_res = await fact_checker.verify_claims(run_id=run_id, retry_budget_remaining=0)

            # -------------------------------------------------------------
            # Stage 5: GENERATING_REPORT (Academic Synthesis)
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.GENERATING_REPORT)
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "agent": "report_writer", "message": "Report Writer Agent generating canonical report..."},
            )

            task_rep = TaskRepository.create(run_id, "report_writer", "Compile Quality-Gated Report with Numbered Citations", {"run_id": run_id})
            try:
                report_res = await report_writer.generate_report(run_id=run_id, research_question=question, is_demo=is_demo_sources)
                TaskRepository.finish(task_rep["id"], "COMPLETED", report_res.model_dump())
            except Exception as e:
                TaskRepository.finish(task_rep["id"], "FAILED", error_message=str(e))
                raise

            # -------------------------------------------------------------
            # Stage 6: EVALUATING & Quality Gates
            # -------------------------------------------------------------
            self._check_cancellation(run_id)
            current_state = self._transition(run_id, current_state, WorkflowState.EVALUATING)
            await broadcaster.broadcast(
                run_id,
                "STATE_CHANGED",
                {"state": current_state.value, "message": "Evaluating quality gates and completion criteria..."},
            )

            # Mark Completed
            current_state = self._transition(run_id, current_state, WorkflowState.COMPLETED)
            RunRepository.update_status(run_id, WorkflowState.COMPLETED.value, completed=True)

            await broadcaster.broadcast(
                run_id,
                "RUN_COMPLETED",
                {
                    "run_id": run_id,
                    "report_id": report_res.report_id,
                    "status": "COMPLETED",
                    "citation_count": report_res.citation_count,
                    "quality_gate_passed": report_res.quality_gate.passed,
                },
            )

            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "report_id": report_res.report_id,
                "quality_gate": report_res.quality_gate.model_dump(),
            }

        except (Exception, asyncio.CancelledError) as e:
            if self.is_cancelled(run_id):
                logger.info("Run %s terminated due to user cancellation.", run_id)
                RunRepository.update_status(run_id, WorkflowState.CANCELLED.value, error_message="Cancelled by user.", completed=True)
                return {"run_id": run_id, "status": "CANCELLED"}

            err_msg = f"{type(e).__name__}: {str(e)}"
            logger.error("Run %s failed at state %s: %s\n%s", run_id, current_state, err_msg, traceback.format_exc())
            RunRepository.update_status(run_id, WorkflowState.FAILED.value, error_message=err_msg, completed=True)
            await broadcaster.broadcast(
                run_id,
                "RUN_FAILED",
                {"run_id": run_id, "error": err_msg, "last_state": current_state.value},
            )
            return {"run_id": run_id, "status": "FAILED", "error": err_msg}

    def _transition(self, run_id: str, current: WorkflowState, target: WorkflowState) -> WorkflowState:
        """Enforces valid state machine transition and persists to database."""
        validate_transition(current, target)
        RunRepository.update_status(run_id, target.value)
        return target

    def _check_cancellation(self, run_id: str) -> None:
        if self.is_cancelled(run_id):
            raise asyncio.CancelledError(f"Run {run_id} was cancelled by user.")


# Global orchestrator instance
orchestrator = ResearchOrchestrator()
