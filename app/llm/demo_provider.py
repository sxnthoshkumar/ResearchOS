"""
Deterministic Demonstration LLM Provider.
Enables full offline workflow tests, realistic agent state transitions, and interactive UI verification
without requiring external AI API keys or network requests.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class DemoLLMProvider(BaseLLMProvider):
    """Provides deterministic, structured JSON responses simulating realistic multi-agent execution."""

    def __init__(self, model_name: str = "demo-deterministic-engine"):
        self.model_name = model_name

    def get_provider_name(self) -> str:
        return "demo"

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 2000,
        response_format_json: bool = False,
    ) -> LLMResponse:
        user_prompt = ""
        system_prompt = ""
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                user_prompt = msg.content

        # Route prompt to appropriate deterministic generator based on keywords
        if "PLANNER AGENT" in system_prompt or "RESEARCH PLAN" in user_prompt.upper():
            content = self._generate_planner_output(user_prompt)
        elif "RELEVANCE EVALUATOR" in system_prompt or "RELEVANCE" in user_prompt.upper():
            content = self._generate_relevance_output(user_prompt)
        elif "ANALYSIS AGENT" in system_prompt or "ATOMIC CLAIMS" in user_prompt.upper():
            content = self._generate_analyst_output(user_prompt)
        elif "FACT-CHECKING AGENT" in system_prompt or "VERIFY" in user_prompt.upper():
            content = self._generate_fact_checker_output(user_prompt)
        elif "REPORT" in system_prompt or "FINAL REPORT" in user_prompt.upper():
            content = self._generate_report_output(user_prompt)
        elif "SINGLE-AGENT BASELINE" in system_prompt or "BASELINE" in user_prompt.upper():
            content = self._generate_baseline_output(user_prompt)
        else:
            content = json.dumps({
                "status": "success",
                "message": "[DEMO MODE] Deterministic agent response generated successfully.",
                "note": "Demonstration execution without external AI key."
            })

        return LLMResponse(
            content=content,
            model=self.model_name,
            prompt_tokens=len(user_prompt.split()) + len(system_prompt.split()),
            completion_tokens=len(content.split()),
            total_tokens=len(user_prompt.split()) + len(content.split()),
            estimated_cost_usd=0.0,
            raw_response={"mode": "demo_deterministic"},
        )

    def _extract_question(self, text: str) -> str:
        match = re.search(r"Research Question:\s*\"?([^\n\"]+)\"?", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return lines[0] if lines else "Comparative Analysis of Domain-Specific AI Methods"

    def _generate_planner_output(self, prompt: str) -> str:
        question = self._extract_question(prompt)
        plan = {
            "plan_id": "plan-demo-001",
            "research_question": question,
            "objectives": [
                f"Evaluate the foundational architectural mechanisms addressing: {question}",
                "Analyze comparative empirical metrics (latency, computational cost, domain accuracy)",
                "Identify practical engineering trade-offs, operational boundaries, and research gaps",
            ],
            "subquestions": [
                {
                    "id": "sq-1",
                    "title": "Architectural Mechanisms & Foundational Principles",
                    "description": f"How do core technical methodologies differ for: {question}?",
                    "search_queries": [
                        f"{question} architecture overview",
                        "retrieval augmented generation vs fine-tuning benchmarks",
                    ],
                    "expected_evidence": "Empirical architectural diagrams, algorithmic formulations, and pipeline latency breakdowns.",
                },
                {
                    "id": "sq-2",
                    "title": "Empirical Performance & Cost Analysis",
                    "description": "What are the comparative tradeoffs in training cost, inference latency, and task accuracy?",
                    "search_queries": [
                        "RAG vs fine-tuning domain adaptation accuracy cost",
                        "retrieval hallucination reduction quantitative metrics",
                    ],
                    "expected_evidence": "Benchmark accuracy comparisons, hardware FLOPS requirements, and response time distributions.",
                },
                {
                    "id": "sq-3",
                    "title": "Limitations, Domain Shift & Future Gaps",
                    "description": "What failure modes and unanswered research questions remain unaddressed?",
                    "search_queries": [
                        "rag knowledge stale context window limitations",
                        "fine tuning catastrophic forgetting domain QA",
                    ],
                    "expected_evidence": "Qualitative error taxonomy, catastrophic forgetting evaluations, and open questions.",
                },
            ],
            "target_sections": [
                "Executive Summary",
                "Methodology & Scope",
                "Architectural Foundations",
                "Comparative Evaluation",
                "Limitations & Vulnerabilities",
                "Open Research Gaps",
                "Conclusion & Recommendations",
            ],
        }
        return json.dumps(plan, indent=2)

    def _generate_relevance_output(self, prompt: str) -> str:
        relevance_data = {
            "direct_relevance": 88.0,
            "methodology_relevance": 82.0,
            "findings_relevance": 84.0,
            "domain_relevance": 90.0,
            "direct_explanation": "Directly examines architectural mechanisms and comparative performance between retrieval-augmented generation and fine-tuning.",
            "methodology_explanation": "Methodology contrasts parametric backpropagation with non-parametric dense vector index queries.",
            "findings_explanation": "Provides quantitative benchmarks on knowledge freshness, inference token latency, and training compute requirements.",
            "domain_explanation": "Directly situates findings within machine learning domain question answering.",
            "positive_signals": ["Direct empirical evaluation of RAG and fine-tuning", "Latency and compute benchmarks"],
            "missing_information": [],
            "excerpts": [
                {
                    "text": "Foundations of Retrieval-Augmented Generation vs Parameter Fine-Tuning",
                    "provenance": "title"
                }
            ]
        }
        return json.dumps(relevance_data, indent=2)

    def _generate_analyst_output(self, prompt: str) -> str:
        # Generate structured claims matching available demo evidence
        claims_data = {
            "summary": "Synthesized empirical comparative claims based on retrieved passages.",
            "claims": [
                {
                    "claim_text": "Retrieval-Augmented Generation dynamically incorporates external knowledge without requiring model parameter updates, substantially reducing upfront training compute.",
                    "claim_type": "factual",
                    "subquestion_id": "sq-1",
                    "section_target": "Architectural Foundations",
                    "evidence_snippet": "RAG systems query parametric and non-parametric indices at inference time, avoiding full weight retraining.",
                },
                {
                    "claim_text": "Fine-tuning deep neural models on domain corpora yields lower per-query token latency but incurs significant GPU training costs and risks catastrophic forgetting.",
                    "claim_type": "comparative",
                    "subquestion_id": "sq-2",
                    "section_target": "Comparative Evaluation",
                    "evidence_snippet": "Full parameter fine-tuning alters attention weights, improving specialized vocabulary comprehension while elevating re-indexing expenditure.",
                },
                {
                    "claim_text": "Hybrid architectures combining lightweight adapter fine-tuning (e.g. LoRA) with dense vector retrieval achieve Pareto-optimal accuracy in clinical and legal question-answering.",
                    "claim_type": "factual",
                    "subquestion_id": "sq-2",
                    "section_target": "Comparative Evaluation",
                    "evidence_snippet": "Integrating parameter-efficient fine-tuning with retrieval mechanisms demonstrates superior factual precision across regulated domains.",
                },
                {
                    "claim_text": "RAG implementations remain sensitive to retrieval noise, context window truncation, and embedding semantic drift across heterogeneous document corpora.",
                    "claim_type": "limitation",
                    "subquestion_id": "sq-3",
                    "section_target": "Limitations & Vulnerabilities",
                    "evidence_snippet": "Top-k retrieval failures inject distractor context into the generator, degrading response veracity.",
                },
            ],
            "limitations_identified": [
                "Most empirical benchmarks evaluate English-centric datasets; multilingual cross-domain performance lacks thorough auditing.",
                "Published latency measurements frequently neglect network round-trip overhead for remote vector stores.",
            ],
        }
        return json.dumps(claims_data, indent=2)

    def _generate_fact_checker_output(self, prompt: str) -> str:
        # If single-claim prompt from FactCheckingAgent
        if "Claim to Audit:" in prompt:
            return json.dumps({
                "verification_status": "SUPPORTED",
                "explanation": "Direct textual alignment confirmed. The retrieved passages explicitly affirm the asserted scientific finding.",
                "exact_supporting_excerpts": ["Direct textual alignment confirmed from retrieved passage."],
                "contradicting_evidence": None,
                "confidence": 0.95
            }, indent=2)

        # Legacy batch verification format
        verdicts = {
            "verifications": [
                {
                    "claim_index": 0,
                    "verdict": "SUPPORTED",
                    "rationale": "Direct textual alignment confirmed. The retrieved passages explicitly affirm that non-parametric retrieval preserves frozen model weights.",
                    "support_score": 0.95,
                    "contradiction_found": False,
                },
                {
                    "claim_index": 1,
                    "verdict": "SUPPORTED",
                    "rationale": "Passage evidence directly corroborates latency reduction at test time alongside increased training FLOPS and catastrophic forgetting risks.",
                    "support_score": 0.90,
                    "contradiction_found": False,
                },
                {
                    "claim_index": 2,
                    "verdict": "PARTIALLY_SUPPORTED",
                    "rationale": "Empirical gains for hybrid LoRA+RAG are documented, but evidence is restricted to specific clinical/legal benchmarks rather than universal domains.",
                    "support_score": 0.72,
                    "contradiction_found": False,
                },
                {
                    "claim_index": 3,
                    "verdict": "SUPPORTED",
                    "rationale": "Retrieval noise and distractor passages are identified as primary error vectors in the audited passages.",
                    "support_score": 0.92,
                    "contradiction_found": False,
                },
            ]
        }
        return json.dumps(verdicts, indent=2)

    def _generate_report_output(self, prompt: str) -> str:
        report_data = {
            "title": "Comprehensive Comparative Evaluation: Architectural, Empirical, and Operational Analysis",
            "executive_summary": "This research investigation provides a rigorous comparison between Retrieval-Augmented Generation (RAG) and domain-specific fine-tuning. Grounded in scholarly evidence, our multi-agent analysis demonstrates that RAG delivers superior factual dynamism and zero retraining cost, while fine-tuning excels in stylistic adherence and reduced per-query prompt overhead. Hybrid architectures are emerging as the predominant enterprise paradigm.",
            "methodology": "A collaborative five-agent architecture performed systematic query formulation, scholarly literature harvesting across academic repositories, atomic claim extraction, adversarial evidence verification, and quality-gated report synthesis.",
            "findings_sections": [
                {
                    "heading": "Architectural Foundations & Knowledge Injection",
                    "content": "RAG separates knowledge storage into external non-parametric document indices, allowing continuous corpus updates without model recompilation [1]. In contrast, fine-tuning modifies internal parametric weights through backpropagation [2].",
                },
                {
                    "heading": "Comparative Empirical Analysis: Latency, Cost, and Accuracy",
                    "content": "Empirical evaluations highlight contrasting operational profiles. While fine-tuned models exhibit predictable inference latency by omitting dynamic index retrieval [2], RAG frameworks mitigate factual hallucination by grounding generations in verified source passages [1]. Hybrid configurations employing parameter-efficient adapters alongside dense retrievers achieve superior domain accuracy [2].",
                },
                {
                    "heading": "Vulnerabilities and Failure Modes",
                    "content": "Primary failure modes in RAG systems stem from retrieval distractors and chunk boundary truncation [1]. Conversely, fine-tuned models are susceptible to hallucinations on out-of-distribution prompts and catastrophic forgetting of pre-training general reasoning skills [2].",
                },
            ],
            "comparison_table": {
                "headers": ["Dimension", "Retrieval-Augmented Generation (RAG)", "Domain Fine-Tuning", "Hybrid (PEFT + RAG)"],
                "rows": [
                    ["Knowledge Freshness", "Real-time dynamic updates", "Static until next retraining run", "Dynamic external + specialized internal"],
                    ["Training Compute", "Zero model retraining compute", "High GPU hours required", "Moderate (parameter-efficient)"],
                    ["Inference Latency", "Higher (retrieval + reranking)", "Low (direct forward pass)", "Moderate"],
                    ["Hallucination Risk", "Low (grounded in context)", "Moderate to High", "Very Low"],
                    ["Data Traceability", "Full passage provenance", "Opaque parametric recall", "Full passage provenance"],
                ],
            },
            "limitations": "Findings are subject to the scope of retrieved academic literature. Empirical benchmarks reflect controlled experimental settings, and actual production latency will vary based on vector database indexing and cluster proximity.",
            "research_gaps": "Future research must address automated verification of multi-hop reasoning in RAG, as well as formal guarantees against catastrophic forgetting in continual domain adaptation.",
            "conclusion": "Neither RAG nor fine-tuning represents a universally superior solution. Optimal system design requires a hybrid approach calibrated against domain update frequency, latency requirements, and budgetary constraints.",
        }
        return json.dumps(report_data, indent=2)

    def _generate_baseline_output(self, prompt: str) -> str:
        # Simulate standard monolithic single-pass generation
        return json.dumps({
            "title": "[BASELINE SINGLE-AGENT] Overview Report",
            "content": "Retrieval-Augmented Generation (RAG) and Fine-Tuning are two main approaches. RAG uses external search while Fine-Tuning updates weights. RAG is cheaper for updates, but Fine-Tuning is faster during inference.",
            "citations_found": 0,
            "verification_performed": False,
            "note": "Single-pass baseline without agent collaboration or verified passage linkage."
        })
