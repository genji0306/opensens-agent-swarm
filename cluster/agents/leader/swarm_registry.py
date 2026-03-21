"""Agent registry for LangGraph swarm construction.

Maps each DarkLab agent to its handler, task_type, device, and
natural-language description for the LLM router.

Descriptions are derived from the corresponding SKILL.md files.
"""
from __future__ import annotations


def get_agent_registry() -> dict:
    """Build the agent registry with lazy handler imports.

    Returns a dict mapping agent names to their specs::

        {"research": {"handler": fn, "task_type": "research",
                       "device": "academic", "description": "..."}, ...}
    """
    from academic.research import handle as research_handle
    from academic.literature import handle as literature_handle
    from academic.doe import handle as doe_handle
    from academic.paper import handle as paper_handle
    from academic.perplexity import handle as perplexity_handle
    from experiment.simulation import handle as simulation_handle
    from experiment.analysis import handle as analysis_handle
    from experiment.synthetic import handle as synthetic_handle
    from experiment.report_data import handle as report_data_handle
    from experiment.autoresearch import handle as autoresearch_handle
    from leader.synthesis import handle as synthesis_handle
    from leader.media_gen import handle as media_gen_handle

    registry = {
        # Academic agents
        "research": {
            "handler": research_handle,
            "task_type": "research",
            "device": "academic",
            "description": (
                "Literature search, gap analysis, and research framework generation. "
                "Produces structured research plans with key findings, gaps, "
                "proposed approaches, and citations via multi-AI cross-validation."
            ),
        },
        "literature": {
            "handler": literature_handle,
            "task_type": "literature",
            "device": "academic",
            "description": (
                "Deep literature review of a specific query. Produces a "
                "comprehensive review of existing work, methodologies, and state of the art."
            ),
        },
        "doe": {
            "handler": doe_handle,
            "task_type": "doe",
            "device": "academic",
            "description": (
                "Design of Experiments planning. Given an experimental specification, "
                "generates a structured DOE with factor levels, response variables, "
                "and statistical design."
            ),
        },
        "paper": {
            "handler": paper_handle,
            "task_type": "paper",
            "device": "academic",
            "description": (
                "Draft a scientific paper or manuscript. Requires prior research findings "
                "and produces structured academic text with abstract, introduction, "
                "methods, results, and discussion sections."
            ),
        },
        "perplexity": {
            "handler": perplexity_handle,
            "task_type": "perplexity",
            "device": "academic",
            "description": (
                "Real-time web research via the Perplexity API. Best for current events, "
                "recent publications, and web-sourced information not in training data."
            ),
        },
        # Experiment agents
        "simulate": {
            "handler": simulation_handle,
            "task_type": "simulate",
            "device": "experiment",
            "description": (
                "Run numerical simulations. Given simulation parameters, runs "
                "physics/chemistry/ML models and returns structured results."
            ),
        },
        "analyze": {
            "handler": analysis_handle,
            "task_type": "analyze",
            "device": "experiment",
            "description": (
                "Analyze experimental or simulation data. Applies statistical methods, "
                "generates visualizations, and extracts key insights from datasets."
            ),
        },
        "synthetic": {
            "handler": synthetic_handle,
            "task_type": "synthetic",
            "device": "experiment",
            "description": (
                "Generate synthetic datasets for testing or training. Creates realistic "
                "data following specified statistical distributions or domain constraints."
            ),
        },
        "report_data": {
            "handler": report_data_handle,
            "task_type": "report_data",
            "device": "experiment",
            "description": (
                "Generate publication-quality data visualizations and figures. "
                "Produces charts, plots, and tables ready for reports or papers."
            ),
        },
        "autoresearch": {
            "handler": autoresearch_handle,
            "task_type": "autoresearch",
            "device": "experiment",
            "description": (
                "Autonomous ML research loops. Runs automated hypothesis-test-evaluate "
                "cycles, hyperparameter searches, and iterative model improvement."
            ),
        },
        # Leader agents
        "synthesize": {
            "handler": synthesis_handle,
            "task_type": "synthesize",
            "device": "leader",
            "description": (
                "Synthesize findings from multiple research and experiment sources "
                "into a coherent narrative with cross-validated summaries."
            ),
        },
        "media_gen": {
            "handler": media_gen_handle,
            "task_type": "media_gen",
            "device": "leader",
            "description": (
                "Generate formatted reports in Word (.docx) or PowerPoint (.pptx) "
                "format from synthesized research findings."
            ),
        },
    }

    # NotebookLM is optional
    try:
        from leader.notebooklm import handle as notebooklm_handle
        registry["notebooklm"] = {
            "handler": notebooklm_handle,
            "task_type": "notebooklm",
            "device": "leader",
            "description": (
                "Generate audio overviews, study guides, or briefing documents "
                "via NotebookLM from source documents."
            ),
        }
    except ImportError:
        pass

    return registry
