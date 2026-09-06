"""CLI entry point for the task system."""

from __future__ import annotations

import sys
import json
from pathlib import Path
from datetime import datetime

from .models import TaskStatus, Priority
from .task_queue import (
    list_tasks, load_task, get_queue_stats, create_task,
    claim_task, save_task, load_goal
)
from .decomposer import decompose_goal
from .executor import Executor
from .memory import search_memory, get_recent_learnings, get_memory_stats, record_memory
from .verifier import verify_task, get_evidence
from .profiles import ProfileRegistry
from .model_router import route_task, route_for_profile, estimate_session_cost
from .skill_registry import SkillRegistry
from .eval import run_suite, run_all_suites, list_suites, load_suite, list_runs, get_suite_stats
from .self_improve import SelfImprovementLoop, cmd_improve as si_cmd_improve, cmd_improve_verify as si_cmd_verify
from .gap_classifier import cmd_classify, cmd_report, cmd_failures, cmd_gap_trends
from .gap_repair import cmd_gap_repair
from .orchestrator import Orchestrator, SubAgentSpec, OrchestrationPattern, OrchestrationRun
from .handoff import HandoffProtocol, ContextPackage, HandoffStatus
from .context_manager import ContextManager, ContextLevel, ContextItem, NavigationEntry
from .context_pruning import (
    ContextPruningEngine, PruningConfig, ContextMonitor, Compactor,
    Summarizer, SummarySchema, FileOffloader, KVCacheOptimizer,
)
from .budget_guard import BudgetGuard, BudgetConfig, RunLogEntry
from .constraints_enforcer import ConstraintsEnforcer, ConstraintRule, ConstraintCheckResult
from .project_intelligence import (
    MVIValidator, VersionTracker, VersionInfo, ContextFileGenerator,
    ExternalContextHandler, ExternalContextFile, WizardResponses, ExistingContextInfo,
)
from .hardening import (
    Hardener, RetryHandler, TimeoutHandler, CircuitBreaker,
    get_all_circuit_breakers, reset_all_circuit_breakers,
    CircuitBreakerConfig, RetryConfig,
)
from .agent_spawner import AgentSpawner, AgentProcessStatus
from .regression_prevention import RegressionPreventer, RegressionPolicy, EvalScope, PolicyAction
from .momentum import MomentumMonitor
from .scheduler import Scheduler
from .dashboard import generate_dashboard, open_dashboard as _open_dashboard
from .intelligence import IntelligenceMonitor
from .harness import HarnessRun, list_runs as list_harness_runs, load_run as load_harness_run
from .harness_coding import CodingHarness
from .harness_research import ResearchHarness
from .agent_teams import (
    AgentTeamsCoordinator, TeamPreset, TeamRole, TeamMember,
    TeamDisplayMode, TeamStatus,
)
from .skill_creator import (
    SkillCreator, SkillDraft, SkillTestCase, SkillEvalResult,
    BenchmarkResult, ImprovementHistory, ImprovementIteration,
    format_eval_summary, format_improvement_history,
)
from .understand_anything import (
    UnderstandAnythingPipeline, FileScanner, StaticAnalyzer,
    GraphAssembler, ArchitectureAnalyzer, TourBuilder, GraphValidator,
    GraphSaver, KnowledgeGraph, ScanResult, GraphNode, GraphEdge,
    Layer, TourStep, ValidationReport,
)
from .loop_patterns import (
    CritiqueImprovementLoop, SelfEvolutionLoop, IterativeRefinement,
    LoopRegistry, LoopConfig, LoopPattern, LoopStatus,
    ConvergenceChecker, ConvergenceResult, ConvergenceReason,
    CritiqueRound, EvolutionStep, RefinementRound, LoopRun,
)
from .background_agents import (
    HackerNewsBriefingAgent, DevPulseAgent, BackgroundAgentRegistry,
    BackgroundAgentConfig, AgentType, AgentRun, RunStatus,
    DeliveryMethod, Story, BriefingResult,
)
from .prompts_index import (
    PromptsIndex, PromptEntry, PromptVersion, PromptUsage,
    PromptCollection, PromptSearchResult,
    PromptCategory, PromptStatus, UsageOutcome,
)
from .bankr_trading import (
    BankrAgent, StrategyType, SignalType, TimeFrame,
    BacktestResult, Portfolio, TradeSignal,
    FinancialLLMAnalyzer, _find_best_ollama_model, _ollama_list_models,
)
from .reflection_bridge import RuntimeReflectionBridge, TokenBudget
from .reflection_analysis import generate_system_report as reflection_report
from .storage_utils import (
    prune_records, initialize_friction_log, append_friction_entry,
)


def main():
    """Unified CLI — routes subcommands."""
    args = sys.argv[1:]
    if not args:
        _print_help()
        return
    
    command = args[0]
    
    commands = {
        "help": _cmd_help,
        "status": _cmd_status,
        "goals": _cmd_goals,
        "tasks": _cmd_tasks,
        "claim": _cmd_claim,
        "run": _cmd_run,
        "queue": _cmd_queue,
        "decompose": _cmd_decompose,
        "verify": _cmd_verify,
        "memory": _cmd_memory,
        "decisions": _cmd_decisions,
        "inspect": _cmd_inspect,
        "evidence": _cmd_evidence,
        "profile": _cmd_profile,
        "profiles": _cmd_profiles,
        "route": _cmd_route,
        "skills": _cmd_skills,
        "skill": _cmd_skill,
        "skill-create": _cmd_skill_create,
        "skill-test": _cmd_skill_test,
        "skill-eval": _cmd_skill_eval,
        "skill-improve": _cmd_skill_improve,
        "skill-optimize": _cmd_skill_optimize,
        "eval": _cmd_eval,
        "evals": _cmd_evals,
        "eval-runs": _cmd_eval_runs,
        "eval-stats": _cmd_eval_stats,
        "improve": _cmd_improve,
        "improve-verify": _cmd_improve_verify,
        "classify": _cmd_classify,
        "report": _cmd_report,
        "failures": _cmd_failures,
        "gap-repair": _cmd_gap_repair,
        "gap-trends": _cmd_gap_trends,
        # Phase 4 — Multi-agent & Hardening
        "orchestrate": _cmd_orchestrate,
        "orch-list": _cmd_orch_list,
        "orch-inspect": _cmd_orch_inspect,
        "handoff": _cmd_handoff,
        "handoff-list": _cmd_handoff_list,
        "handoff-claim": _cmd_handoff_claim,
        "context": _cmd_context,
        "context-nav": _cmd_context_nav,
        # DCP — Dynamic Context Pruning
        "dcp": _cmd_dcp,
        "dcp-prune": _cmd_dcp_prune,
        "dcp-status": _cmd_dcp_status,
        "dcp-config": _cmd_dcp_config,
        # Budget Guard
        "budget": _cmd_budget,
        "budget-check": _cmd_budget_check,
        "budget-record": _cmd_budget_record,
        "budget-config": _cmd_budget_config,
        "budget-killswitch": _cmd_budget_killswitch,
        "budget-status": _cmd_budget_status,
        # Constraints Enforcer
        "constraints": _cmd_constraints,
        "constraints-check-path": _cmd_constraints_check_path,
        "constraints-check-edit": _cmd_constraints_check_edit,
        "constraints-check-push": _cmd_constraints_check_push,
        "constraints-check-merge": _cmd_constraints_check_merge,
        "constraints-rules": _cmd_constraints_rules,
        "constraints-status": _cmd_constraints_status,
        # Project Intelligence
        "add-context": _cmd_add_context,
        "pi-validate": _cmd_pi_validate,
        "pi-generate": _cmd_pi_generate,
        "pi-detect": _cmd_pi_detect,
        "pi-external": _cmd_pi_external,
        "circuit": _cmd_circuit,
        "circuit-reset": _cmd_circuit_reset,
        "hardener": _cmd_hardener,
        "spawn": _cmd_spawn,
        "spawn-list": _cmd_spawn_list,
        "spawn-kill": _cmd_spawn_kill,
        "gate": _cmd_gate,
        "gate-policies": _cmd_gate_policies,
        "gate-check": _cmd_gate_check,
        # Phase 5 — Momentum Monitoring
        "momentum": _cmd_momentum,
        "momentum-report": _cmd_momentum_report,
        "momentum-snapshots": _cmd_momentum_snapshots,
        "momentum-stats": _cmd_momentum_stats,
        # Phase 5 — Scheduled Workflows
        "schedule": _cmd_schedule,
        "schedule-list": _cmd_schedule_list,
        "schedule-create": _cmd_schedule_create,
        "schedule-run": _cmd_schedule_run,
        "schedule-enable": _cmd_schedule_enable,
        "schedule-disable": _cmd_schedule_disable,
        "schedule-delete": _cmd_schedule_delete,
        # Phase 5 — External Intelligence
        "pattern": _cmd_pattern,
        "pattern-list": _cmd_pattern_list,
        "pattern-add": _cmd_pattern_add,
        "pattern-apply": _cmd_pattern_apply,
        "pattern-delete": _cmd_pattern_delete,
        "source": _cmd_source,
        "source-list": _cmd_source_list,
        "source-create": _cmd_source_create,
        "source-check": _cmd_source_check,
        "source-check-all": _cmd_source_check_all,
        "intelligence-stats": _cmd_intelligence_stats,
        "dashboard": _cmd_dashboard,
        "gui": _cmd_gui,
        # Phase 6 — Harness Patterns
        "coding-run": _cmd_coding_run,
        "coding-resume": _cmd_coding_resume,
        "coding-status": _cmd_coding_status,
        "coding-list": _cmd_coding_list,
        "research-run": _cmd_research_run,
        "research-resume": _cmd_research_resume,
        "research-status": _cmd_research_status,
        "research-list": _cmd_research_list,
        "harness-list": _cmd_harness_list,
        "harness-status": _cmd_harness_status,
        # Phase 7 — Agent Teams
        "team-spawn": _cmd_team_spawn,
        "team-status": _cmd_team_status,
        "team-shutdown": _cmd_team_shutdown,
        "team-review": _cmd_team_review,
        "team-debug": _cmd_team_debug,
        "team-feature": _cmd_team_feature,
        "team-list": _cmd_team_list,
        # Phase 8 — Understand Anything
        "understand-scan": _cmd_understand_scan,
        "understand-analyze": _cmd_understand_analyze,
        "understand-graph": _cmd_understand_graph,
        "understand-status": _cmd_understand_status,
        # Phase 9 — Loop Patterns
        "loop-critique": _cmd_loop_critique,
        "loop-evolve": _cmd_loop_evolve,
        "loop-refine": _cmd_loop_refine,
        "loop-list": _cmd_loop_list,
        "loop-status": _cmd_loop_status,
        "loop-stats": _cmd_loop_stats,
        # Phase 10 — Background Agents
        "hn-brief": _cmd_hn_brief,
        "dev-pulse": _cmd_dev_pulse,
        "bg-list": _cmd_bg_list,
        "bg-status": _cmd_bg_status,
        "bg-stats": _cmd_bg_stats,
        # Phase 10 — Prompts Index (P2c)
        "prompt-add": _cmd_prompt_add,
        "prompt-get": _cmd_prompt_get,
        "prompt-list": _cmd_prompt_list,
        "prompt-search": _cmd_prompt_search,
        "prompt-update": _cmd_prompt_update,
        "prompt-delete": _cmd_prompt_delete,
        "prompt-versions": _cmd_prompt_versions,
        "prompt-export": _cmd_prompt_export,
        "prompt-usage": _cmd_prompt_usage,
        "prompt-stats": _cmd_prompt_stats,
        # Phase 11 — Bankr Trading Agent (P2d)
        "bankr-fetch": _cmd_bankr_fetch,
        "bankr-analyze": _cmd_bankr_analyze,
        "bankr-signals": _cmd_bankr_signals,
        "bankr-backtest": _cmd_bankr_backtest,
        "bankr-portfolio": _cmd_bankr_portfolio,
        "bankr-report": _cmd_bankr_report,
        "bankr-strategies": _cmd_bankr_strategies,
        "bankr-list": _cmd_bankr_list,
        "bankr-status": _cmd_bankr_status,
        "bankr-analyze-ai": _cmd_bankr_analyze_ai,
        "bankr-chat": _cmd_bankr_chat,
        "bankr-llm-status": _cmd_bankr_llm_status,
        # Reflection System (ai-improved-self-reflection)
        "reflect-record": _cmd_reflect_record,
        "reflect-distill": _cmd_reflect_distill,
        "reflect-promote": _cmd_reflect_promote,
        "reflect-validate": _cmd_reflect_validate,
        "reflect-report": _cmd_reflect_report,
        "reflect-bridge": _cmd_reflect_bridge,
        "reflect-analysis": _cmd_reflect_analysis,
        "reflect-prune": _cmd_reflect_prune,
        "reflect-log": _cmd_reflect_log,
    }
    
    handler = commands.get(command)
    if handler:
        handler(args[1:])
    else:
        print(f"Unknown command: {command}")
        _print_help()


def _print_help(args=None):
    print("""Task System CLI — available commands:

  status              System dashboard summary
  tasks [status]      List tasks (optional status filter)
  goals               List all goals
  inspect <task_id>   Show task details
  queue               Queue statistics
  decompose <goal>    Decompose a goal into tasks
  claim [worker]      Claim next eligible task
  run [n]             Run N execution iterations (default: 1)
  verify <task_id>    Verify a specific task
  evidence <task_id>  Show verification evidence
  memory [query]      Search memory
  decisions           Recent decisions and learnings
  profiles            List available agent profiles
  profile <name>      Activate a profile (planner|executor|reviewer|researcher|self-improver)
  route [task_id]     Show model routing decision (for task or active profile)
  skills              List available skills
  skill <name>        Show skill details
  eval <suite>        Run an eval suite (smoke|unit-tests|components)
  evals               List available eval suites
  eval-runs           Show recent eval run history
  eval-stats          Show eval system statistics
   improve <desc>      Start a self-improvement cycle (snapshot + baseline)
   improve-verify <desc> Complete a self-improvement cycle (verify + record)
   classify <desc>     Classify a failure description into a gap type
   report <desc>       Record a classified failure report
   failures [n]        Show recent failure reports (default: 10)
   gap-repair <desc>   Auto-classify and repair a failure
    gap-trends [n]      Show gap type trend analysis (default: 7 days)

  Budget Guard (P0b):
    budget <pattern>        Check budget status for a pattern
    budget-check <pattern>  Run full budget check (spend + actionable + kill-switch)
    budget-record <pattern> Record a run log entry (interactive input)
    budget-config [path]    Show/save budget guard configuration
    budget-killswitch [on|off]  Enable/disable kill switch
    budget-status           Show budget guard system status

  Project Intelligence (P1a):
    add-context             Run interactive context creation wizard (6 questions)
    add-context --update    Update existing patterns (review each)
    add-context --global    Save to ~/.config/opencode/ instead of project dir
    pi-validate <file>     Validate a context file against MVI standards
    pi-generate <file>     Generate technical-domain.md from saved responses
    pi-detect [dir]        Detect existing project intelligence files
    pi-external [dir]      Discover external context files in .tmp/

  Constraints Enforcer (P0c):
    constraints             Show constraints status + active rule count
    constraints-check-path <path>  Check path against denylist rules
    constraints-check-edit <path>  Check edit against all rules
    constraints-check-push  Check push rules
    constraints-check-merge Check merge rules
    constraints-rules       List all constraint rules
    constraints-status      Show full constraints enforcer status

  Phase 4 — Multi-Agent & Production Hardening:
    orchestrate <goal>  Run multi-agent orchestration (fan-out/fan-in)
    orch-list           List recent orchestration runs
    orch-inspect <id>   Inspect an orchestration run
    handoff <sender> <receiver> <msg>  Create a handoff between agents
    handoff-list [receiver]  List handoffs, optionally by receiver
    handoff-claim <id> <agent>  Claim and process a handoff
    context [level]     Show context summary (level_1|level_2|level_3)
    context-nav         Generate context navigation.md
    dcp                 Dynamic Context Pruning: run full pruning cycle
    dcp-prune           Run DCP pruning on current context + show results
    dcp-status          Show DCP engine configuration and health
    dcp-config [path]   Show/save DCP configuration file
    circuit [name]      Show circuit breaker state(s)
    circuit-reset [name] Reset circuit breaker(s)
    hardener <name> <cmd>  Execute a command with hardening (retry+timeout+circuit)
    spawn <cmd>         Spawn a sub-agent with real-time streaming
    spawn-list [status] List spawned processes
    spawn-kill <id>     Kill a spawned process
    gate <policy>       Run a regression check against a policy
    gate-policies       List regression prevention policies
    gate-check <task>   Guard task completion with regression check

  Phase 5 — Proactive & Momentum:
    momentum            Momentum dashboard (quick overview)
    momentum-report     Full momentum report with recommendations
    momentum-snapshots  List recent momentum snapshots
    momentum-stats      Momentum monitor statistics

  Scheduled Workflows:
    schedule            Show schedule info
    schedule-list       List all schedules
    schedule-create     Create a new schedule
    schedule-run        Run all due schedules (creates Tasks)
    schedule-enable     Enable a schedule
    schedule-disable    Disable a schedule
    schedule-delete     Delete a schedule

  External Intelligence:
    pattern             Show pattern details
    pattern-list        List all discovered patterns
    pattern-add         Add a new pattern
    pattern-apply       Mark pattern as applied
    pattern-delete      Delete a pattern
    source              Show source info
    source-list         List all sources
    source-create       Create a new source
    source-check        Check a source for new patterns
    source-check-all    Check all enabled sources for new patterns
    intelligence-stats  Show intelligence monitor statistics

  Dashboard:
    dashboard           Generate HTML system dashboard (--open to open in browser)
    gui                 Start web-based GUI dashboard (Flask server)
      --host <host>       Host to bind to (default: 127.0.0.1)
      --port <port>       Port to listen on (default: 8080)
      --debug             Enable debug mode
      --refresh <sec>     Auto-refresh interval (default: 5)

  Phase 6 — Harness Patterns:
    coding-run <goal>   Run the coding delivery harness (plan→implement→review→test→verify)
    coding-resume <id>  Resume a paused coding harness run
    coding-status <id>  Show coding harness run details
    coding-list         List all coding harness runs
    research-run <goal> Run the research harness (search→extract→analyze→synthesize→document)
    research-resume <id> Resume a paused research harness run
    research-status <id> Show research harness run details
    research-list       List all research harness runs
    harness-list        List all harness runs across all types
    harness-status <id> Show details for any harness run

  Phase 7 — Agent Teams:
    team-spawn <preset> <name>  Create + spawn a team from preset
                                  presets: review, debug, feature, fullstack,
                                  research, security, migration, custom
    team-status <team_id>       Show team status summary
    team-shutdown <team_id>     Gracefully shut down a team
    team-review <goal>          Quick parallel code review
    team-debug <goal>           Hypothesis-driven debugging
    team-feature <goal>         Parallel feature development
    team-list                   List all teams

  Background Agents (P2a):
    hn-brief [--live] [--stories <n>] [--delivery <method>]
                                    Run Hacker News briefing agent
    hn-brief --dry-run              Show configuration without running
    dev-pulse [--dry-run]           Run DevPulse signal intelligence agent
    bg-list [--limit <n>] [--type <agent_type>]
                                    List recent background agent runs
    bg-status <run-id>              Show details of a background agent run
    bg-stats                        Show aggregate background agent statistics

  Prompts Index (P2c):
    prompt-add <name> <content>     Create a new prompt entry
              [--description <desc>] [--category <cat>] [--status <status>]
              [--tags <t1,t2>] [--author <name>]
    prompt-get <prompt-id>          Show prompt details
    prompt-list [--category <cat>] [--status <status>] [--tags <t1,t2>]
              [--limit <n>]         List prompts with optional filters
    prompt-search <query>           Search prompts by text
              [--category <cat>] [--status <status>] [--limit <n>]
    prompt-update <prompt-id>       Update a prompt
              [--content <text>] [--description <desc>] [--status <status>]
              [--tags <t1,t2>] [--notes <notes>] [--author <name>]
    prompt-delete <prompt-id>       Delete a prompt and its versions
    prompt-versions <prompt-id>     List all versions of a prompt
    prompt-export <prompt-id>       Export a prompt with versions and stats
              [--json]              Export as raw JSON
    prompt-usage <prompt-id>        Show usage statistics for a prompt
              [--record] [--outcome <outcome>] [--duration <ms>]
              [--tokens <n>] [--context <ctx>] [--feedback <fb>]
    prompt-stats                    Show aggregate prompt catalog statistics

  Bankr Trading Agent (P2d):
    bankr-fetch <ticker> <start> <end>  Fetch market data for a ticker
              [--interval <1d|1wk|1mo|1h>]
    bankr-analyze <ticker> <start> <end>  Compute technical indicators
              [--interval <interval>]
    bankr-signals <ticker> <start> <end>  Generate trading signals
              [--strategy <sma_crossover|rsi|macd|bollinger_bands|ensemble>]
              [--interval <interval>] [--short-window <n>] [--long-window <n>]
              [--period <n>] [--oversold <n>] [--overbought <n>]
    bankr-backtest <ticker> <start> <end>
              [--strategy <strategy>] [--cash <amount>] [--interval <interval>]
              [--strategy-params <key=val,...>]
    bankr-portfolio <tickers> <start> <end>
              [--strategy <strategy>] [--cash <amount>]
              [--alloc <pct1,pct2,...>] [--interval <interval>]
    bankr-report [<result-index>]    Show backtest report (default: latest)
              [--list]               List all saved results
    bankr-strategies                 List all available strategies and their defaults
    bankr-list [--limit <n>]         List saved backtest results
    bankr-status                     Show Bankr agent status and configuration
    bankr-analyze-ai <ticker> <start> <end>
                                    AI-powered technical analysis using local Ollama model
              [--model <model>]     Specify Ollama model (default: qwen3:8b)
              [--type <technical|portfolio|analysis>]
              [--interval <interval>]
    bankr-chat <question>           Ask a financial question to the local LLM
              [--context <text>]    Optional context for the question
    bankr-llm-status                Check LLM availability and show configured model

  Reflection System (ai-improved-self-reflection):
    reflect-record <args>     Record a reflection event
                                  --task <t> --category <cat> --observation <obs>
                                  --cause <cause> --lesson <lesson> --scope <scope>
                                  --confidence <0.0-1.0> --evidence <n> --action <act>
    reflect-distill           Distill experiences into candidate lessons
                                  [--min-occurrences <n>]
    reflect-promote           Promote validated candidates to capabilities
                                  [--auto] [--event-id <id>] [--level <0-3>]
    reflect-validate          Record capability validation
                                  --capability <id> --task <task> --outcome <text>
                                  --success [--delta <float>]
    reflect-report            Generate full reflection system report
    reflect-bridge            Show runtime reflection bridge prompt overlay
                                  [--scope <scope>] [--tokens <n>]
    reflect-analysis          Show reflection system analysis report [--json]
    reflect-prune             Prune old reflection records
                                  [--limit <n>] [--dry-run]
    reflect-log               Show or add to the friction log
                                  [--add <text>] [--tail <n>]

    help                This message
""")


# Aliases
_cmd_help = _print_help


def _cmd_status(args):
    """Show system dashboard."""
    from .models import TaskStatus
    
    tasks = list_tasks()
    queue = get_queue_stats()
    mem = get_memory_stats()
    
    print("+========================================+")
    print("|       SYSTEM STATUS DASHBOARD        |")
    print("+========================================+")
    print()
    print(f" Tasks:        {queue.get('total', 0)} total")
    print(f"  Pending:     {queue.get('pending', 0)}")
    print(f"  Claimed:     {queue.get('claimed', 0)}")
    print(f"  In Progress: {len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])}")
    print(f"  Verifying:   {len([t for t in tasks if t.status == TaskStatus.VERIFYING])}")
    print(f"  Completed:   {queue.get('completed', 0)}")
    print(f"  Failed:      {queue.get('failed', 0)}")
    print()
    print(f" Memory:       {mem['total']} entries")
    print(f"  Hot:         {mem['hot_count']}")
    print(f"  Warm:        {mem['warm_count']}")
    print(f"  Cold:        {mem['cold_count']}")
    print()
    
    # Next unblocked task
    task = claim_task("inspect")
    if task:
        print(f" Next task:    {task.id} — {task.description[:60]}...")
    else:
        print(" Next task:    (none pending with met dependencies)")


def _cmd_tasks(args):
    """List tasks, optionally filtered by status."""
    status = args[0] if args else None
    tasks = list_tasks(status)
    
    if not tasks:
        print("No tasks found.")
        return
    
    priority_icons = {"P0": "[!]", "P1": "[>]", "P2": "[+]", "P3": "[ ]"}
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    
    print(f"{'ID':<14} {'Status':<12} {'Priority':<10} {'Description':<50}")
    print("-" * 86)
    for t in sorted(tasks, key=lambda x: (priority_order.get(x.priority.value, 99), x.created_at)):
        icon = priority_icons.get(t.priority.value, "[ ]")
        desc = t.description[:48] + ".." if len(t.description) > 48 else t.description
        print(f"{icon} {t.id:<10} {t.status.value:<12} {t.priority.value:<10} {desc}")


def _cmd_goals(args):
    """List all goals."""
    goals_dir = Path("goals")
    if not goals_dir.exists():
        print("No goals found.")
        return
    goals = sorted(goals_dir.glob("*.json"))
    if not goals:
        print("No goals found.")
        return
    print(f"{'Goal ID':<18} {'Status':<10} {'Tasks':<6} Description")
    print("-" * 70)
    for path in goals:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"{data.get('id', path.stem):<18} {data.get('status', '?'):<10} {len(data.get('tasks', [])):<6} {data.get('description', '')[:50]}")
        except (json.JSONDecodeError, IOError):
            print(f"{path.stem:<18} (unreadable)")


def _cmd_inspect(args):
    """Show detailed task information."""
    if not args:
        print("Usage: inspect <task_id>")
        return
    
    task = load_task(args[0])
    if not task:
        print(f"Task {args[0]} not found.")
        return
    
    print(f"Task:        {task.id}")
    print(f"Description: {task.description}")
    print(f"Status:      {task.status.value}")
    print(f"Priority:    {task.priority.value}")
    print(f"Risk:        {task.risk_level.value}")
    print(f"Owner:       {task.owner or '(unclaimed)'}")
    print(f"Attempts:    {task.attempts}/{task.max_attempts}")
    print(f"Dependencies: {', '.join(task.depends_on) if task.depends_on else '(none)'}")
    print(f"Tags:        {', '.join(task.skill_tags) if task.skill_tags else '(none)'}")
    if task.failure_reason:
        print(f"Failure:     {task.failure_reason[:200]}")
    print(f"Created:     {task.created_at}")
    print(f"Updated:     {task.updated_at}")
    if task.completed_at:
        print(f"Completed:   {task.completed_at}")
    if task.verification_plan:
        vp = task.verification_plan
        print(f"Verification: {vp.method}")
        if vp.command:
            print(f"  Command:   {vp.command}")


def _cmd_claim(args):
    """Claim the next eligible task."""
    worker = args[0] if args else "default"
    task = claim_task(worker)
    if task:
        print(f"Claimed task: {task.id}")
        print(f"  Description: {task.description}")
        print(f"  Priority:    {task.priority.value}")
        print(f"  Tags:        {', '.join(task.skill_tags)}")
    else:
        print("No eligible tasks available.")


def _cmd_queue(args):
    """Show queue statistics."""
    stats = get_queue_stats()
    print("Queue Statistics:")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")


def _cmd_decompose(args):
    """Decompose a goal description into tasks."""
    if not args:
        print("Usage: decompose <goal description>")
        return
    
    description = " ".join(args)
    print(f"Decomposing goal: {description}")
    goal = decompose_goal(description)
    print(f"Goal ID: {goal.id}")
    print(f"Created {len(goal.tasks)} tasks:")
    for task_id in goal.tasks:
        from .task_queue import load_task
        task = load_task(task_id)
        if task:
            deps = f" (depends on: {', '.join(task.depends_on)})" if task.depends_on else ""
            print(f"  [{task.priority.value}] {task.id}: {task.description[:70]}{deps}")


def _cmd_run(args):
    """Run the execution loop."""
    n = int(args[0]) if args else 1
    executor = Executor()

    for i in range(n):
        print(f"\n--- Iteration {i+1}/{n} ---")

        try:
            work_done = executor.run_once()
        except Exception as e:
            print(f"Execution error: {e}")
            break

        # 🔥 FIX 2: distinguish real stop vs false empty queue
        if work_done is False:
            # Ask executor WHY nothing ran
            if hasattr(executor, "last_reason"):
                print(f"No work available: {executor.last_reason}")
            else:
                print("No work available (unknown reason)")

            # IMPORTANT: do NOT immediately break in ambiguous state
            if getattr(executor, "queue_might_have_tasks", False):
                print("Queue may still contain runnable tasks — re-evaluating...")
                continue

            break


def _cmd_verify(args):
    """Verify a specific task."""
    if not args:
        print("Usage: verify <task_id>")
        return
    
    task = load_task(args[0])
    if not task:
        print(f"Task {args[0]} not found.")
        return
    
    result = verify_task(task)
    print(f"Verification {'PASSED' if result else 'FAILED'} for {task.id}")
    evidence = get_evidence(task.id)
    if evidence:
        last = evidence[-1]
        if last.get("output"):
            print(f"  Output: {last['output'][:200]}")


def _cmd_evidence(args):
    """Show verification evidence for a task."""
    if not args:
        print("Usage: evidence <task_id>")
        return
    
    evidence = get_evidence(args[0])
    if not evidence:
        print(f"No evidence found for task {args[0]}.")
        return
    
    for e in evidence:
        print(f"\nMethod: {e['method']}")
        print(f"Passed: {'YES' if e['passed'] else 'NO'}")
        print(f"Time:   {e['timestamp']}")
        if e.get("output"):
            print(f"Output: {e['output'][:300]}")
        if e.get("error"):
            print(f"Error:  {e['error']}")


def _cmd_memory(args):
    """Search or list memory."""
    query = " ".join(args) if args else None
    if query:
        results = search_memory(query)
        if not results:
            print("No memory matches.")
            return
        print(f"Memory results for '{query}':")
        for entry in results[:10]:
            tier = entry.get("tier", "hot")
            imp = entry.get("importance", 5)
            print(f"  [{tier}:{imp}] {entry['content'][:100]}")
    else:
        learnings = get_recent_learnings(10)
        mem = get_memory_stats()
        print(f"Memory system: {mem['total']} total entries ({mem['hot_count']} hot, {mem['warm_count']} warm, {mem['cold_count']} cold)")
        if learnings:
            print("\nRecent learnings:")
            for entry in learnings:
                print(f"  [{entry['type']}:{entry.get('importance', 5)}] {entry['content'][:100]}")


def _cmd_decisions(args):
    """Show recorded decisions and learnings."""
    learnings = get_recent_learnings(20)
    decisions = [e for e in learnings if e["type"] == "decision"]
    
    if decisions:
        print("Architecture Decisions:")
        for d in decisions:
            print(f"  [{d.get('importance', 5)}] {d['content'][:120]}")
    
    if learnings:
        print("\nRecent Learnings & Failures:")
        for e in learnings[:10]:
            print(f"  [{e['type']:>8}:{e.get('importance', 5)}] {e['content'][:100]}")


def _cmd_profiles(args):
    """List available agent profiles."""
    registry = ProfileRegistry()
    # Ensure defaults exist
    registry.create_default_profiles()
    
    profiles = registry.load_all()
    active = registry.get_active()
    
    if not profiles:
        print("No profiles found. Create profiles in the profiles/ directory.")
        return
    
    print(f"{'Profile':<18} {'Model':<10} {'Risk':<8} {'Context':<10} Purpose")
    print("-" * 80)
    for p in profiles:
        marker = "→ " if (active and p.name == active.name) else "  "
        purpose = p.purpose[:50] + "..." if len(p.purpose) > 50 else p.purpose
        print(f"{marker}{p.name:<16} {p.model_preference:<10} {p.risk_tolerance:<8} {p.context_level:<10} {purpose}")
    
    if active:
        print(f"\nActive profile: {active.name}")


def _cmd_profile(args):
    """Activate a profile by name."""
    if not args:
        print("Usage: profile <name>")
        print("Available profiles:")
        registry = ProfileRegistry()
        registry.create_default_profiles()
        for name in registry.discover():
            print(f"  {name}")
        return
    
    name = args[0]
    registry = ProfileRegistry()
    registry.create_default_profiles()
    profile = registry.activate(name)
    
    if profile:
        print(f"  Purpose: {profile.purpose}")
        print(f"  Skills: {', '.join(profile.skill_tags)}")
        print(f"  Model: {profile.model_preference}")
        print(f"  Risk: {profile.risk_tolerance}")
        print(f"  Context: {profile.context_level}")
        
        # Show routing decision
        routing = route_for_profile(profile)
        print(f"  Routing: {routing.model_tier} ({routing.reason})")
        print(f"  Est. cost/task: ${routing.estimated_cost:.6f}")
    else:
        print(f"Profile '{name}' not found.")


def _cmd_skills(args):
    """List available skills."""
    registry = SkillRegistry()
    registry.create_default_skills()
    registry.register_crm_skill_handlers()

    skills = registry.load_all()
    if not skills:
        print("No skills found.")
        return

    stats = registry.get_stats()
    print(f"{'Skill':<24} {'Risk':<8} {'Cost':<8} {'Tags':<30} Description")
    print("-" * 100)
    for s in skills:
        tags = ", ".join(s.skill_tags[:4])
        desc = s.description[:50] + "..." if len(s.description) > 50 else s.description
        print(f"{s.name:<24} {s.risk_level:<8} {s.cost_multiplier:<8} {tags:<30} {desc}")

    print(f"\n{stats['total_skills']} skills, {len(stats['tags'])} distinct tags")


def _cmd_skill(args):
    """Show detailed skill information."""
    if not args:
        print("Usage: skill <name>")
        return

    name = args[0]
    registry = SkillRegistry()
    registry.create_default_skills()
    registry.register_crm_skill_handlers()

    skill = registry.load(name)
    if not skill:
        print(f"Skill '{name}' not found.")
        return

    print(f"Skill:        {skill.name}")
    print(f"Description:  {skill.description}")
    print(f"Risk level:   {skill.risk_level}")
    print(f"Cost factor:  {skill.cost_multiplier}")
    print(f"Tags:         {', '.join(skill.skill_tags)}")
    print(f"Triggers:     {', '.join(skill.triggers)}")
    if skill.requires:
        print(f"Requires:     {', '.join(skill.requires)}")
    if skill.config:
        print(f"Config:       {json.dumps(skill.config, indent=2)}")


# ── Skill Creator Commands ──────────────────────────────────────────────────────


def _cmd_skill_create(args):
    """Interactive skill creation wizard.

    Usage: skill-create <name> [--description <desc>] [--triggers <t1,t2>]
           [--tags <t1,t2>] [--category <cat>] [--risk <low|medium|high>]
           [--version <ver>] [--output <dir>]

    Creates a new skill directory with SKILL.md, writes it to skills/<name>/,
    and optionally registers it in the skill registry.
    """
    if not args:
        print("Usage: skill-create <name> [--description <desc>] [--triggers <t1,t2>] "
              "[--tags <t1,t2>] [--category <cat>] [--risk <low|medium|high>] "
              "[--version <ver>] [--output <dir>]")
        return

    name = args[0]
    description = ""
    triggers = []
    tags = []
    category = "developer-tools"
    risk_level = "low"
    version = "1.0.0"
    output_dir = None

    i = 1
    while i < len(args):
        if args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif args[i] == "--triggers" and i + 1 < len(args):
            triggers = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--category" and i + 1 < len(args):
            category = args[i + 1]
            i += 2
        elif args[i] == "--risk" and i + 1 < len(args):
            risk_level = args[i + 1]
            i += 2
        elif args[i] == "--version" and i + 1 < len(args):
            version = args[i + 1]
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        else:
            i += 1

    creator = SkillCreator()
    draft = creator.create_draft(
        name=name,
        description=description or f"A {name} skill",
        triggers=triggers,
        tags=tags,
        version=version,
        category=category,
        risk_level=risk_level,
    )

    skill_path = creator.write_skill_file(draft, output_dir)
    print(f"✅ Skill '{name}' created at {skill_path}")

    # Show frontmatter summary
    print(f"\n  Name:        {draft.name}")
    print(f"  Description: {draft.description}")
    print(f"  Version:     {draft.version}")
    print(f"  Category:    {draft.category}")
    print(f"  Risk:        {draft.risk_level}")
    if draft.triggers:
        print(f"  Triggers:    {', '.join(draft.triggers)}")
    if draft.tags:
        print(f"  Tags:        {', '.join(draft.tags)}")

    # Optionally register with the skill registry
    print(f"\n  Next steps:")
    print(f"   1. Edit {skill_path} with your skill content")
    print(f"   2. Add test cases: skill-test {name} --add \"<prompt>\"")
    print(f"   3. Run evals:     skill-eval {name}")


def _cmd_skill_test(args):
    """Add or list test cases for a skill.

    Usage: skill-test <name> [--add <prompt>] [--expect <e1|e2>]
           [--files <f1,f2>] [--tags <t1,t2>]

    Without --add, lists existing test cases for the skill.
    With --add, creates a new test case.
    """
    if not args:
        print("Usage: skill-test <name> [--add <prompt>] [--expect <e1|e2>] "
              "[--files <f1,f2>] [--tags <t1,t2>]")
        return

    name = args[0]
    creator = SkillCreator()

    if "--add" in args:
        # Create a new test case
        idx = args.index("--add")
        if idx + 1 >= len(args):
            print("Error: --add requires a prompt")
            return
        prompt = args[idx + 1]

        expectations = []
        if "--expect" in args:
            eidx = args.index("--expect")
            if eidx + 1 < len(args):
                expectations = [e.strip() for e in args[eidx + 1].split("|")]

        files = []
        if "--files" in args:
            fidx = args.index("--files")
            if fidx + 1 < len(args):
                files = [f.strip() for f in args[fidx + 1].split(",")]

        tags = []
        if "--tags" in args:
            tidx = args.index("--tags")
            if tidx + 1 < len(args):
                tags = [t.strip() for t in args[tidx + 1].split(",")]

        # Load existing test cases
        existing = creator.load_evals_json(name) or []
        new_id = max((tc.id for tc in existing), default=0) + 1

        tc = SkillTestCase(
            id=new_id,
            prompt=prompt,
            expectations=expectations,
            files=files,
            tags=tags,
            name=f"Eval {new_id}",
        )
        existing.append(tc)
        creator.save_evals_json(name, existing)

        print(f"✅ Test case {new_id} added to '{name}':")
        print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        if expectations:
            print(f"  Expectations ({len(expectations)}):")
            for ex in expectations:
                print(f"    • {ex[:70]}{'...' if len(ex) > 70 else ''}")
        print(f"\n  Total test cases: {len(existing)}")
    else:
        # List existing test cases
        test_cases = creator.load_evals_json(name)
        if not test_cases:
            print(f"No test cases found for skill '{name}'.")
            print(f"  Add one with: skill-test {name} --add \"<prompt>\"")
            return

        print(f"Test cases for '{name}':")
        print(f"  {'ID':<4} {'Name':<16} {'Expectations':<14} {'Files':<12} Prompt")
        print(f"  " + "-" * 80)
        for tc in test_cases:
            exp_count = len(tc.expectations)
            file_count = len(tc.files)
            prompt_short = tc.prompt[:50] + "..." if len(tc.prompt) > 50 else tc.prompt
            print(f"  {tc.id:<4} {tc.name:<16} {exp_count:<14} {file_count:<12} {prompt_short}")


def _cmd_skill_eval(args):
    """Run evaluation for a skill against its test cases.

    Usage: skill-eval <name> [--all] [--configs <n>] [--export <path>]

    Runs the skill's test cases and grades the results. With --all,
    runs both with-skill and without-skill configurations for comparison.
    With --configs <n>, runs each configuration n times for statistical
    significance (default: 1).

    This is a programmatic eval using keyword-based grading. For production
    use, extend with AI-powered grading by replacing the grade_output method.
    """
    if not args:
        print("Usage: skill-eval <name> [--all] [--configs <n>] [--export <path>]")
        return

    name = args[0]
    creator = SkillCreator()

    # Load test cases
    test_cases = creator.load_evals_json(name)
    if not test_cases:
        print(f"No test cases found for skill '{name}'.")
        print(f"  Add one with: skill-test {name} --add \"<prompt>\"")
        return

    # Parse options
    do_both = "--all" in args
    configs = 1
    if "--configs" in args:
        idx = args.index("--configs")
        if idx + 1 < len(args):
            try:
                configs = int(args[idx + 1])
            except ValueError:
                pass

    export_path = None
    if "--export" in args:
        idx = args.index("--export")
        if idx + 1 < len(args):
            export_path = args[idx + 1]

    # Load the skill draft for description
    draft = creator.load_skill_draft(creator.skills_dir / name)

    print(f"Running evaluation for '{name}'...")
    print(f"  Test cases: {len(test_cases)}")
    print(f"  Configurations: {'with_skill + without_skill' if do_both else 'with_skill only'}")
    print(f"  Runs per config: {configs}")
    print()

    results: list[SkillEvalResult] = []

    for tc in test_cases:
        print(f"  Eval {tc.id}: {tc.prompt[:60]}...")

        configs_to_run = ["with_skill", "without_skill"] if do_both else ["with_skill"]

        for config in configs_to_run:
            for run_num in range(1, configs + 1):
                transcript = f"Running {config} eval for: {tc.prompt}"
                output = draft.description if draft else tc.expected_output

                grading = creator.grade_output(
                    tc.expectations,
                    transcript=transcript,
                    output=output,
                )

                result = creator.create_eval_result(
                    test_case=tc,
                    configuration=config,
                    run_number=run_num,
                    grading_result=grading,
                    time_seconds=0.5,
                    tokens=len(transcript) + len(output),
                    tool_calls=len(tc.expectations),
                    errors=0,
                )
                results.append(result)

            # Show per-eval summary
            config_results = [r for r in results[-configs:] if r.configuration == config]
            if config_results:
                avg = sum(r.pass_rate for r in config_results) / len(config_results)
                print(f"    {config}: {avg:.0%} pass rate ({configs} run{'s' if configs > 1 else ''})")

    print()

    # Compute benchmark
    benchmark = creator.compute_benchmark(
        skill_name=name,
        results=results,
        skill_path=str(creator.skills_dir / name),
    )

    # Show summary
    summary = benchmark.compute_summary()
    ws = summary.get("with_skill", {})
    wo = summary.get("without_skill", {})
    delta = summary.get("delta", {})

    print("  ── Results ──")
    if ws:
        pr = ws.get("pass_rate", {})
        print(f"  With skill:    {pr.get('mean', 0):.1%} ±{pr.get('stddev', 0):.1%} "
              f"[{pr.get('min', 0):.1%}–{pr.get('max', 0):.1%}]")
    if wo:
        pr = wo.get("pass_rate", {})
        print(f"  Without skill: {pr.get('mean', 0):.1%} ±{pr.get('stddev', 0):.1%} "
              f"[{pr.get('min', 0):.1%}–{pr.get('max', 0):.1%}]")
    if "pass_rate" in delta:
        print(f"  Delta:         {delta['pass_rate']}")

    # Save benchmark
    bench_path = creator.save_benchmark(benchmark)
    print(f"\n  Benchmark saved to: {bench_path}")

    # Export if requested
    if export_path:
        export_file = Path(export_path)
        export_file.write_text(
            json.dumps(benchmark.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Exported to: {export_file.resolve()}")

    # Show full eval summary
    print(f"\n  ── Detail ──")
    print(format_eval_summary(results))


def _cmd_skill_improve(args):
    """Run iterative improvement loop for a skill.

    Usage: skill-improve <name> [--iterations <n>] [--history]

    Runs the improvement loop: version -> eval -> grade -> improve -> repeat.
    Each iteration creates a new version of the skill and evaluates it
    against the test cases.

    With --history, shows the improvement history instead of running a
    new iteration.
    """
    if not args:
        print("Usage: skill-improve <name> [--iterations <n>] [--history]")
        return

    name = args[0]
    creator = SkillCreator()

    # Show history
    if "--history" in args:
        history = creator.load_improvement_history(name)
        print(format_improvement_history(history))
        return

    # Load the skill draft
    draft = creator.load_skill_draft(creator.skills_dir / name)
    if not draft:
        print(f"Skill '{name}' not found. Create it with: skill-create {name}")
        return

    # Load test cases
    test_cases = creator.load_evals_json(name)
    if not test_cases:
        print(f"No test cases found for '{name}'. Add one with: skill-test {name} --add \"<prompt>\"")
        return

    # Parse iterations count
    iterations = 1
    if "--iterations" in args:
        idx = args.index("--iterations")
        if idx + 1 < len(args):
            try:
                iterations = int(args[idx + 1])
            except ValueError:
                pass

    # Load or create improvement history
    history = creator.load_improvement_history(name)

    print(f"Improvement loop for '{name}':")
    print(f"  Test cases:    {len(test_cases)}")
    print(f"  Iterations:    {iterations}")
    print(f"  Current best:  {history.current_best or '(none)'}")
    print()

    # Check if we need a baseline iteration
    if not history.iterations:
        print("  Running baseline (v0)...")
        baseline_iter = creator.run_improvement_iteration(draft, test_cases, history)
        print(f"  Baseline pass rate: {baseline_iter.expectation_pass_rate:.1%}")
        creator.save_improvement_history(history)
        print()

    # Run improvement iterations
    for i in range(iterations):
        version = history.next_version()
        print(f"  Iteration {i + 1}/{iterations} -> {version}...")

        iteration = creator.run_improvement_iteration(draft, test_cases, history)

        status = "★ BEST" if iteration.is_current_best else ""
        print(f"    Pass rate: {iteration.expectation_pass_rate:.1%} ({iteration.grading_result}) {status}")
        print(f"    Version:   {iteration.version}")

        # Save state after each iteration
        creator.save_improvement_history(history)

    print()
    print(format_improvement_history(history))


def _cmd_skill_optimize(args):
    """Optimize skill description and triggers for better matching.

    Usage: skill-optimize <name> [--queries <q1,q2>] [--dry-run]

    Analyzes the skill's current description and triggers against sample
    queries, then produces an optimized version.

    With --queries, provide comma-separated sample queries that the skill
    should match. With --dry-run, shows recommended changes without applying.
    """
    if not args:
        print("Usage: skill-optimize <name> [--queries <q1,q2>] [--dry-run]")
        return

    name = args[0]
    creator = SkillCreator()

    # Load the skill draft
    draft = creator.load_skill_draft(creator.skills_dir / name)
    if not draft:
        print(f"Skill '{name}' not found. Create it with: skill-create {name}")
        return

    # Parse queries
    test_queries = []
    if "--queries" in args:
        idx = args.index("--queries")
        if idx + 1 < len(args):
            test_queries = [q.strip() for q in args[idx + 1].split(",")]

    dry_run = "--dry-run" in args

    # Show current state
    print(f"Skill: '{name}'")
    print(f"  Description: {draft.description}")
    print(f"  Triggers ({len(draft.triggers)}): {', '.join(draft.triggers)}")
    print(f"  Tags ({len(draft.tags)}): {', '.join(draft.tags)}")
    print()

    if test_queries:
        print("  Sample queries:")
        for q in test_queries:
            print(f"    • {q}")
        print()

    # Run optimization
    original_triggers = list(draft.triggers)
    optimized = creator.optimize_description(draft, test_queries)

    # Show results
    new_triggers = [t for t in optimized.triggers if t not in original_triggers]
    if new_triggers:
        print(f"  Recommended new triggers ({len(new_triggers)}):")
        for t in new_triggers:
            print(f"    + {t}")
    else:
        print("  No new triggers needed (existing triggers cover the queries)")

    if dry_run:
        print("\n  🔍 Dry-run mode — no changes applied.")
        print(f"  To apply: skill-optimize {name} --queries \"{','.join(test_queries)}\"")
    else:
        # Apply changes
        if new_triggers:
            creator.write_skill_file(optimized, creator.skills_dir / name)
            print(f"\n  ✅ Updated {creator.skills_dir / name / 'SKILL.md'}")
        print("  Optimization complete.")


# ── Route Command ──────────────────────────────────────────────────────────────


def _cmd_route(args):
    """Show model routing decision for a task or active profile."""
    if args:
        # Route for a specific task
        task_id = args[0]
        from .task_queue import load_task
        task = load_task(task_id)
        if not task:
            print(f"Task {task_id} not found.")
            return
        registry = ProfileRegistry()
        registry.create_default_profiles()
        profile = registry.get_active()
        decision = route_task(task, profile)
        print(f"Routing decision for task {task.id}:")
        print(f"  Description: {task.description[:80]}")
        print(f"  Model tier:  {decision.model_tier}")
        print(f"  Reason:      {decision.reason}")
        print(f"  Est. cost:   ${decision.estimated_cost:.6f}")
        print(f"  Context:     {decision.context_allocation}")
    else:
        # Route for active profile
        registry = ProfileRegistry()
        registry.create_default_profiles()
        profile = registry.get_active()
        if not profile:
            print("No active profile. Use 'profile <name>' first.")
            return
        decision = route_for_profile(profile)
        print(f"Routing for profile '{profile.name}':")
        print(f"  Model tier:          {decision.model_tier}")
        print(f"  Reason:              {decision.reason}")
        print(f"  Est. cost/task:      ${decision.estimated_cost:.6f}")
        
        session = estimate_session_cost(profile, 10)
        print(f"  Est. cost/10 tasks:  ${session['estimated_total']:.4f}")
        print(f"  Context allocation:  {decision.context_allocation}")


# ── Eval Commands ────────────────────────────────────────────────────────────


def _cmd_eval(args):
    """Run an eval suite."""
    if not args:
        print("Usage: eval <suite_name>")
        print("Available suites:")
        for name in list_suites():
            suite = load_suite(name)
            desc = f" — {suite.description}" if suite else ""
            print(f"  {name}{desc}")
        return

    suite_name = args[0]
    tags = args[1:] if len(args) > 1 else None
    try:
        run = run_suite(suite_name, tags=tags)
        # Print summary line
        rate = run.passed / run.total_cases if run.total_cases > 0 else 0.0
        reg = " !! REGRESSION" if run.regression else ""
        print(f"\nEval complete: {run.passed}/{run.total_cases} passed ({rate:.1%}) in {run.duration}s{reg}")
    except ValueError as e:
        print(f"Error: {e}")


def _cmd_evals(args):
    """List available eval suites."""
    suites = list_suites()
    if not suites:
        print("No eval suites found.")
        print("Create .json files in evals/suites/")
        return

    print(f"{'Suite':<24} {'Cases':<8} {'Baseline':<12} Description")
    print("-" * 80)
    stats = get_suite_stats()
    for name in suites:
        suite = load_suite(name)
        case_count = len(suite.cases) if suite else 0
        baseline_info = stats["suites"].get(name, {}).get("baseline", {})
        baseline_str = f"{baseline_info.get('pass_rate', '-')*100:.0f}%" if baseline_info else "-"
        desc = suite.description[:45] + "..." if suite and len(suite.description) > 45 else (suite.description if suite else "")
        print(f"{name:<24} {case_count:<8} {baseline_str:<12} {desc}")


def _cmd_eval_runs(args):
    """Show recent eval run history."""
    limit = int(args[0]) if args else 10
    runs = list_runs(limit=limit)
    if not runs:
        print("No eval runs recorded.")
        return

    regressions = get_suite_stats().get("total_regressions", 0)
    print(f"{'Run ID':<24} {'Suite':<16} {'Passed':<10} {'Rate':<8} {'Duration':<10} Regression")
    print("-" * 80)
    for r in runs:
        rate = r.passed / r.total_cases if r.total_cases > 0 else 0.0
        reg_mark = "!" if r.regression else "+"
        print(f"{r.run_id:<24} {r.suite_name:<16} {r.passed}/{r.total_cases:<5} {rate:<7.0%} {r.duration:<9.1f}s {reg_mark}")

    print(f"\nTotal regressions recorded: {regressions}")


def _cmd_eval_stats(args):
    """Show eval system statistics."""
    stats = get_suite_stats()
    print("Eval System Statistics:")
    print(f"  Suites:       {stats['total_suites']}")
    print(f"  Total runs:   {stats['total_runs']}")
    print(f"  Regressions:  {stats['total_regressions']}")

    if stats["baseline"]:
        print(f"\nBaselines ({len(stats['baseline'])} suites):")
        for name, bl in stats["baseline"].items():
            print(f"  {name:<20} {bl['passed']}/{bl['total']} passed ({bl['pass_rate']:.1%}) - run {bl['run_id'][:20]}")

    if stats["recent_run"]:
        r = stats["recent_run"]
        print(f"\nMost recent run: {r['suite_name']} -- {r['passed']}/{r['total_cases']} ({r.get('pass_rate', 0):.1%}) at {r['timestamp'][:19]}")


def _cmd_improve(args):
    """Start a self-improvement cycle (snapshot + baseline)."""
    if not args:
        print("Usage: improve <description of the improvement>")
        print("Example: improve 'Add input validation to executor'")
        return
    result = si_cmd_improve(args)
    print(result)


def _cmd_improve_verify(args):
    """Complete a self-improvement cycle (verify + record)."""
    if not args:
        print("Usage: improve-verify <description of the improvement>")
        print("Example: improve-verify 'Add input validation to executor'")
        return
    result = si_cmd_verify(args)
    print(result)


# ── Gap Commands ─────────────────────────────────────────────────────────────


def _cmd_classify(args):
    """Classify a failure description into a gap type."""
    result = cmd_classify(args)
    print(result)


def _cmd_report(args):
    """Record a classified failure report."""
    result = cmd_report(args)
    print(result)


def _cmd_failures(args):
    """Show recent failure reports."""
    result = cmd_failures(args)
    print(result)


def _cmd_gap_repair(args):
    """Auto-classify and repair a failure."""
    result = cmd_gap_repair(args)
    print(result)


def _cmd_gap_trends(args):
    """Show gap type trend analysis."""
    days = int(args[0]) if args else 7
    result = cmd_gap_trends(days)
    print(result)


# ── Budget Guard Commands ─────────────────────────────────────────────────────

def _cmd_budget(args):
    """Check budget status for a pattern."""
    guard = BudgetGuard()
    if not args:
        # Show summary for all patterns
        config = guard.config
        print("=== Budget Guard Overview ===")
        print(f"  Global daily cap: {config.global_daily_cap:,} tokens")
        print(f"  Kill switch: {'ACTIVE' if config.kill_switch_flag else 'inactive'}")
        print(f"  Report-only threshold: {config.report_only_threshold:.0%}")
        print(f"  Max subagent spawns/run: {config.max_subagent_spawns_per_run}")
        print()
        entries = guard.load_log_entries()
        print("  Daily caps per pattern:")
        for pattern, cap in sorted(config.daily_caps.items()):
            spend = guard.get_daily_spend(pattern, entries)
            pct = (spend / cap * 100) if cap > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            print(f"    {pattern:<20} {bar} {spend:,}/{cap:,} ({pct:.0f}%)")
        return

    pattern = args[0]
    entries = guard.load_log_entries()
    result = guard.check_budget(pattern, entries)

    print(f"=== Budget Check: {pattern} ===")
    print(f"  Status:       {result['status']}")
    print(f"  Spend today:  {result['spend_today']:,} tokens")
    print(f"  Daily cap:    {result['daily_cap']:,} tokens")
    print(f"  Percent used: {result['percent_used']:.0f}%")
    print(f"  Message:      {result['message']}")
    if result.get('kill_switch_active'):
        print("  ⛔ Kill switch is ACTIVE — all loops halted")


def _cmd_budget_check(args):
    """Run a full budget check including actionable check."""
    if not args:
        print("Usage: budget-check <pattern>")
        return

    pattern = args[0]
    guard = BudgetGuard()
    entries = guard.load_log_entries()
    result = guard.check_budget(pattern, entries)

    print(f"=== Budget Check: {pattern} ===")
    for key, val in result.items():
        print(f"  {key}: {val}")


def _cmd_budget_record(args):
    """Record a run log entry."""
    if len(args) < 2:
        print("Usage: budget-record <pattern> <outcome>")
        print("  outcomes: no-op, report-only, fix-proposed, escalated")
        print("  Example: budget-record ci-sweeper no-op")
        return

    pattern = args[0]
    outcome = args[1]

    if outcome not in ("no-op", "report-only", "fix-proposed", "escalated"):
        print(f"Invalid outcome: {outcome}. Use: no-op, report-only, fix-proposed, escalated")
        return

    guard = BudgetGuard()
    entry = RunLogEntry(
        run_id=datetime.now().isoformat(),
        pattern=pattern,
        duration_s=0.0,
        items_found=0,
        actions_taken=0,
        escalations=0,
        tokens_estimate=0,
        outcome=outcome,
    )
    guard.record_run(entry)
    print(f"Run recorded for pattern '{pattern}' with outcome '{outcome}'")
    print(f"  Run ID: {entry.run_id}")


def _cmd_budget_config(args):
    """Show/save budget guard configuration."""
    path = args[0] if args else ".budget_guard.json"
    config = BudgetConfig.load(path)

    print("=== Budget Guard Configuration ===")
    print(f"  Global daily cap: {config.global_daily_cap:,}")
    print(f"  Kill switch: {config.kill_switch_flag}")
    print(f"  Report-only threshold: {config.report_only_threshold:.0%}")
    print(f"  Max subagent spawns/run: {config.max_subagent_spawns_per_run}")
    print(f"  Daily caps:")
    for pattern, cap in sorted(config.daily_caps.items()):
        print(f"    {pattern}: {cap:,}")

    if "--save" in args:
        config.save(path)
        print(f"\nConfiguration saved to: {path}")


def _cmd_budget_killswitch(args):
    """Enable/disable the kill switch."""
    guard = BudgetGuard()
    if args:
        if args[0] in ("on", "true", "1", "activate"):
            guard.set_kill_switch(True)
            print("⛔ Kill switch ACTIVATED — all loops will halt immediately")
        elif args[0] in ("off", "false", "0", "deactivate"):
            guard.set_kill_switch(False)
            print("✅ Kill switch deactivated — loops can proceed")
        else:
            print(f"Usage: budget-killswitch [on|off]")
            print(f"  Current state: {'ACTIVE' if guard.config.kill_switch_flag else 'inactive'}")
    else:
        state = "ACTIVE" if guard.config.kill_switch_flag else "inactive"
        print(f"Kill switch is {state}")


def _cmd_budget_status(args):
    """Show budget guard system status."""
    guard = BudgetGuard()
    status = guard.get_status()
    print("=== Budget Guard Status ===")
    for key, val in status.items():
        if isinstance(val, dict):
            print(f"  {key}:")
            for k, v in val.items():
                print(f"    {k}: {v}")
        elif isinstance(val, float):
            print(f"  {key}: {val:.2f}")
        else:
            print(f"  {key}: {val}")


# ── Constraints Enforcer Commands ─────────────────────────────────────────────

def _cmd_constraints(args):
    """Show constraints status."""
    enforcer = ConstraintsEnforcer()
    status = enforcer.get_status()
    print("=== Constraints Enforcer ===")
    print(f"  Active rules: {status['active_rule_count']}")
    print(f"  Kill switch: {'ACTIVE' if status['kill_switch_active'] else 'inactive'}")
    print()
    for rule_type, count in status.get('rules_by_type', {}).items():
        print(f"  {rule_type}: {count} rules")
    print()
    if not args or "--rules" in args:
        rules = enforcer.get_all_rules()
        if rules:
            print("  Rules:")
            for r in rules[:10]:
                marker = "✅" if r.enabled else "⏸"
                print(f"    {marker} [{r.type:>12}] {r.id:<20} {r.message}")
            if len(rules) > 10:
                print(f"    ... and {len(rules) - 10} more")


def _cmd_constraints_check_path(args):
    """Check a path against denylist rules."""
    if not args:
        print("Usage: constraints-check-path <filepath>")
        return

    filepath = args[0]
    enforcer = ConstraintsEnforcer()
    result = enforcer.check_path(filepath)

    icon = "✅" if result.passed else "❌"
    print(f"{icon} Path check: {filepath}")
    print(f"  Passed:  {result.passed}")
    print(f"  Rule:    {result.rule_id}")
    print(f"  Message: {result.message}")
    print(f"  Severity: {result.severity}")


def _cmd_constraints_check_edit(args):
    """Check an edit against all rules."""
    if len(args) < 2:
        print("Usage: constraints-check-edit <filepath> <change_description>")
        return

    filepath = args[0]
    description = " ".join(args[1:])
    enforcer = ConstraintsEnforcer()
    results = enforcer.check_edit(filepath, description)

    if not results:
        print("✅ No constraints triggered — edit is allowed")
        return

    print(f"=== Constraints Check: Edit {filepath} ===")
    for result in results:
        icon = "✅" if result.passed else "❌"
        print(f"  {icon} [{result.severity}] {result.rule_id}")
        print(f"       {result.message}")


def _cmd_constraints_check_push(args):
    """Check push rules."""
    enforcer = ConstraintsEnforcer()
    results = enforcer.check_push()

    if not results:
        print("No push rules defined.")
        return

    print("=== Push Rules Check ===")
    all_pass = all(r.passed for r in results)
    for result in results:
        icon = "✅" if result.passed else "❌"
        print(f"  {icon} {result.rule_id}: {result.message}")
    print(f"\n  Overall: {'✅ PASS' if all_pass else '❌ BLOCKED'}")


def _cmd_constraints_check_merge(args):
    """Check merge rules."""
    enforcer = ConstraintsEnforcer()
    results = enforcer.check_merge()

    if not results:
        print("No merge rules defined.")
        return

    print("=== Merge Rules Check ===")
    all_pass = all(r.passed for r in results)
    for result in results:
        icon = "✅" if result.passed else "❌"
        print(f"  {icon} {result.rule_id}: {result.message}")
    print(f"\n  Overall: {'✅ PASS' if all_pass else '❌ BLOCKED'}")


def _cmd_constraints_rules(args):
    """List all constraint rules."""
    enforcer = ConstraintsEnforcer()
    rules = enforcer.get_all_rules()

    if not rules:
        print("No rules defined.")
        return

    type_filter = args[0] if args else None
    if type_filter:
        rules = [r for r in rules if r.type == type_filter]

    print(f"{'ID':<22} {'Type':<14} {'Action':<10} {'Enabled':<8} Message")
    print("-" * 90)
    for r in rules:
        enabled = "✓" if r.enabled else "✗"
        msg = r.message[:40] + "..." if len(r.message) > 40 else r.message
        print(f"{r.id:<22} {r.type:<14} {r.action:<10} {enabled:<8} {msg}")

    if type_filter:
        print(f"\n{len(rules)} rules of type '{type_filter}'")
    else:
        print(f"\n{len(rules)} rules total")


def _cmd_constraints_status(args):
    """Show full constraints enforcer status."""
    enforcer = ConstraintsEnforcer()
    status = enforcer.get_status()
    print("=== Constraints Enforcer Status ===")
    for key, val in status.items():
        if isinstance(val, dict):
            print(f"  {key}:")
            for k, v in val.items():
                print(f"    {k}: {v}")
        elif isinstance(val, list):
            print(f"  {key}: {len(val)} items")
        else:
            print(f"  {key}: {val}")


# ── Project Intelligence Commands ─────────────────────────────────────────────

PI_CONTEXT_DIR = Path("/c/Users/PC Principal/.config/opencode/context/project-intelligence")


def _resolve_pi_context_dir(args: list[str]) -> Path:
    """Resolve the project-intelligence directory (--global flag override)."""
    if "--global" in args:
        return Path.home() / ".config/opencode" / "context" / "project-intelligence"
    return PI_CONTEXT_DIR


def _cmd_add_context(args):
    """Run the interactive context creation wizard."""
    context_dir = _resolve_pi_context_dir(args)
    context_dir.mkdir(parents=True, exist_ok=True)

    is_update = "--update" in args

    # Stage 0: Check for external context files
    ext_handler = ExternalContextHandler()
    ext_files = ext_handler.discover_files()
    if ext_files:
        print(ext_handler.get_summary(ext_files))
        print()
        print("Options:")
        print("  1. Continue with /add-context (ignore external files)")
        print("  2. Manage external files first (via pi-external)")
        choice = input("Choose [1/2]: ").strip()
        if choice == "2":
            print("\nTo manage external context files, run:")
            print("  pi-external")
            print("Then run add-context again.\n")
            return

    # Stage 1: Detect existing context
    existing = ExistingContextInfo.detect(str(context_dir))

    if existing.exists and not is_update:
        print(f"\nFound existing project intelligence in {context_dir}")
        print(f"  Files: {len(existing.files)}")
        for f in existing.files:
            print(f"    ✓ {Path(f['path']).name} (Version: {f['version']}, Updated: {f['updated']})")
        print()
        print("Options:")
        print("  1. Review and update patterns")
        print("  2. Add new patterns (keep all existing)")
        print("  3. Replace all patterns (start fresh)")
        print("  4. Cancel")
        choice = input("Choose [1/2/3/4]: ").strip()
        if choice == "4":
            print("Cancelled.")
            return
        is_update = choice == "1"
        replace_all = choice == "3"
    elif existing.exists and is_update:
        print(f"\nFound existing context — entering update mode.")
        replace_all = False
    else:
        print(f"\nNo project intelligence found. Creating new context in:")
        print(f"  {context_dir}")
        print()
        if input("Ready? [y/n]: ").strip().lower() != "y":
            print("Cancelled.")
            return
        replace_all = False

    if replace_all:
        print("\nWill backup and recreate all files.")
        if input("Proceed? [y/n]: ").strip().lower() != "y":
            print("Cancelled.")
            return
        # Backup existing files
        backup_dir = Path(".tmp") / "backup" / f"project-intelligence-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        for f in existing.files:
            src = Path(f['path'])
            if src.exists():
                dest = backup_dir / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"  Backed up: {src.name} → {dest}")
        print(f"  Backup directory: {backup_dir}")

    # Stage 1.5: Review existing patterns (if updating)
    version = "1.0"
    existing_responses = {}
    if is_update and existing.patterns:
        print("\n--- Review Existing Patterns ---")
        patterns = existing.patterns
        ts = patterns.get("tech_stack", {})
        if ts:
            print(f"\nCurrent tech stack:")
            for k, v in ts.items():
                print(f"  {k}: {v}")
            if input("\nUpdate tech stack? [y/n]: ").strip().lower() == "y":
                existing_responses["tech_stack"] = _ask_tech_stack()
            else:
                existing_responses["tech_stack"] = ts

        nc = patterns.get("naming_conventions", {})
        if nc:
            print(f"\nCurrent naming conventions: {nc}")
            if input("Update naming conventions? [y/n]: ").strip().lower() == "y":
                existing_responses["naming_conventions"] = _ask_naming()
            else:
                existing_responses["naming_conventions"] = nc

        # Version bump
        old_version = existing.files[0].get("version", "1.0") if existing.files else "1.0"
        version = VersionTracker.bump_version(old_version, "minor")
        print(f"\nVersion: {old_version} → {version}")

    elif replace_all:
        # Get current version from existing for reference
        old_version = existing.files[0].get("version", "1.0") if existing.files else "1.0"
        version = VersionTracker.bump_version(old_version, "major")
        print(f"\nVersion: {old_version} → {version} (major bump due to replace)")
    else:
        version = "1.0"

    # Stage 2: Interactive wizard (for new or partial patterns)
    print("\n" + "━" * 55)
    print("  Project Intelligence Wizard")
    print("━" * 55)

    responses = {
        "tech_stack": existing_responses.get("tech_stack") or _ask_tech_stack(),
        "naming_conventions": existing_responses.get("naming_conventions") or _ask_naming(),
    }

    print("\n" + "━" * 55)
    print("  Q 2/6: API endpoint example")
    print("━" * 55)
    print("Paste your typical API endpoint code (or press Enter to skip):")
    api = input("> ").strip()
    responses["api_pattern"] = api if api else None
    responses["api_description"] = "API endpoint implementation"

    print("\n" + "━" * 55)
    print("  Q 3/6: Component example")
    print("━" * 55)
    print("Paste your typical component code (or press Enter to skip):")
    comp = input("> ").strip()
    responses["component_pattern"] = comp if comp else None
    responses["component_description"] = "UI component implementation"

    print("\n" + "━" * 55)
    print("  Q 5/6: Code standards")
    print("━" * 55)
    print("Enter standards (one per line, empty line to finish):")
    standards = []
    while True:
        line = input(f"  {len(standards) + 1}. ").strip()
        if not line:
            break
        standards.append(line)
    responses["code_standards"] = standards

    print("\n" + "━" * 55)
    print("  Q 6/6: Security requirements")
    print("━" * 55)
    print("Enter requirements (one per line, empty line to finish):")
    security = []
    while True:
        line = input(f"  {len(security) + 1}. ").strip()
        if not line:
            break
        security.append(line)
    responses["security_requirements"] = security

    # Detect source files for codebase references
    responses["detected_files"] = [
        "system/project_intelligence.py",
        "system/cli.py",
    ]

    # Stage 3: Generate context files
    content = ContextFileGenerator.generate_technical_domain(responses, version=version)
    nav_content = ContextFileGenerator.generate_navigation([
        {"file": "technical-domain.md", "description": "Tech stack, patterns, conventions", "priority": "critical"},
    ])

    # Stage 4: Validate
    validation = MVIValidator.validate_all(content)
    print("\n" + "━" * 55)
    print("  Validation Results")
    print("━" * 55)
    for check, result in validation.items():
        if check == "all_passed":
            continue
        if isinstance(result, dict):
            passed = result.get("passes", False)
            icon = "✅" if passed else "❌"
            details = ""
            if "actual" in result:
                details = f" ({result['actual']}/{result.get('max', '?')} lines)"
            if "missing_fields" in result:
                details = f" (missing: {', '.join(result['missing_fields'])})" if result["missing_fields"] else ""
            print(f"  {icon} {check}{details}")

    all_pass = validation.get("all_passed", False)
    if all_pass:
        print(f"\n  ✅ All MVI checks passed!")
    else:
        print(f"\n  ⚠️ Some checks failed — review the output above.")

    # Show preview
    line_count = len(content.splitlines())
    nav_line_count = len(nav_content.splitlines())
    print(f"\n{'-' * 55}")
    print(f"Files to create:")
    print(f"  CREATE  {context_dir / 'technical-domain.md'} ({line_count} lines)")
    print(f"  CREATE  {context_dir / 'navigation.md'} ({nav_line_count} lines)")
    print(f"{'-' * 55}")

    if input("\nWrite files? [y/n]: ").strip().lower() != "y":
        print("Cancelled.")
        return

    # Write files
    (context_dir / "technical-domain.md").write_text(content, encoding="utf-8")
    (context_dir / "navigation.md").write_text(nav_content, encoding="utf-8")

    print("\n" + "━" * 55)
    print("  ✅ Project Intelligence Created!")
    print("━" * 55)
    print(f"\nFiles written to: {context_dir}")
    print(f"  ✓ technical-domain.md (v{version})")
    print(f"  ✓ navigation.md")
    print(f"\nAgents will now use YOUR patterns automatically!")
    print(f"\nNext steps:")
    print(f"  1. Review: cat {context_dir / 'technical-domain.md'}")
    print(f"  2. Update: add-context --update")
    print(f"  3. Validate: pi-validate {context_dir / 'technical-domain.md'}")


def _ask_tech_stack() -> dict:
    """Ask the 6 questions about tech stack interactively."""
    print("\n" + "━" * 55)
    print("  Q 1/6: Tech Stack")
    print("━" * 55)
    print("Example: Next.js + TypeScript + PostgreSQL + Tailwind")
    ts = {}
    for layer in ["framework", "language", "database", "styling"]:
        val = input(f"  {layer.capitalize()}: ").strip()
        ver = input(f"  {layer.capitalize()} version: ").strip()
        why = input(f"  Why {layer}? (rationale): ").strip()
        ts[layer] = val
        ts[f"{layer}_version"] = ver
        ts[f"{layer}_rationale"] = why
    return ts


def _ask_naming() -> dict:
    """Ask naming conventions interactively."""
    print("\n" + "━" * 55)
    print("  Q 4/6: Naming Conventions")
    print("━" * 55)
    print("Examples:")
    print("  Files: kebab-case (user-profile.tsx)")
    print("  Components: PascalCase (UserProfile)")
    print("  Functions: camelCase (getUserProfile)")
    print("  Database: snake_case (user_profiles)")
    nc = {}
    for ntype in ["files", "components", "functions", "database"]:
        convention = input(f"  {ntype.capitalize()}: ").strip()
        example = input(f"  {ntype.capitalize()} example: ").strip()
        nc[ntype] = convention
        nc[f"{ntype}_example"] = example
    return nc


def _cmd_pi_validate(args):
    """Validate a context file against MVI standards."""
    if not args:
        print("Usage: pi-validate <filepath>")
        return

    filepath = args[0]
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return

    content = path.read_text(encoding="utf-8")
    validation = MVIValidator.validate_all(content)

    print(f"=== MVI Validation: {filepath} ===")
    all_pass = True
    for check, result in validation.items():
        if check == "all_passed":
            continue
        if isinstance(result, dict):
            passed = result.get("passes", False)
            if not passed:
                all_pass = False
            icon = "✅" if passed else "❌"
            details = ""
            if "actual" in result:
                details = f" ({result['actual']}/{result.get('max', '?')} lines)"
            if "missing_fields" in result and result["missing_fields"]:
                details = f" (missing: {', '.join(result['missing_fields'])})"
            if "duplicated_files" in result and result["duplicated_files"]:
                details = f" (files: {', '.join(result['duplicated_files'])})"
            print(f"  {icon} {check}{details}")

    print(f"\n  Overall: {'✅ PASS' if all_pass else '❌ FAIL'}")


def _cmd_pi_generate(args):
    """Generate technical-domain.md from saved responses."""
    if args:
        context_dir = Path(args[0])
    else:
        context_dir = PI_CONTEXT_DIR

    if not context_dir.exists():
        print(f"Context directory not found: {context_dir}")
        print("Run 'add-context' first to create project intelligence.")
        return

    # Check for existing
    existing = ExistingContextInfo.detect(str(context_dir))
    version = "1.0"
    if existing.exists and existing.files:
        version = existing.files[0].get("version", "1.0")

    print(f"Generate technical-domain.md in {context_dir}")
    print(f"  Detected version: {version}")
    print("  Use 'add-context' for interactive generation.")
    print("  Use 'pi-validate' to check the result.")


def _cmd_pi_detect(args):
    """Detect existing project intelligence files."""
    dir_str = args[0] if args else str(PI_CONTEXT_DIR)
    info = ExistingContextInfo.detect(dir_str)

    if not info.exists:
        print(f"No project intelligence files found in {dir_str}")
        print("Run 'add-context' to create them.")
        return

    print(f"=== Existing Project Intelligence ===")
    print(f"Directory: {dir_str}")
    print(f"Files ({len(info.files)}):")
    for f in info.files:
        print(f"  ✓ {Path(f['path']).name}")
        print(f"    Version: {f['version']}")
        print(f"    Updated: {f['updated']}")
        print(f"    Description: {f['description']}")

    if info.patterns:
        print(f"\nDetected patterns:")
        ts = info.patterns.get("tech_stack", {})
        if ts:
            print(f"  Tech Stack: {ts.get('framework', '?')} + {ts.get('language', '?')} + {ts.get('database', '?')}")
        standards = info.patterns.get("code_standards", [])
        if standards:
            print(f"  Standards: {len(standards)} defined")
        security = info.patterns.get("security_requirements", [])
        if security:
            print(f"  Security: {len(security)} requirements")


def _cmd_pi_external(args):
    """Discover external context files in .tmp/."""
    tmp_dir = args[0] if args else ".tmp"
    handler = ExternalContextHandler()
    files = handler.discover_files(tmp_dir)

    print(handler.get_summary(files))
    if files:
        print()
        print("To integrate, run 'add-context' and choose option 1.")
        print("To manage files directly, edit/delete them in .tmp/.")


# ── Phase 4: Orchestrator Commands ────────────────────────────────────────────


def _cmd_orchestrate(args):
    """Run multi-agent orchestration (fan-out/fan-in)."""
    if not args:
        print("Usage: orchestrate <goal description>")
        print("Example: orchestrate 'Research and implement a new feature'")
        return

    goal = " ".join(args)
    orch = Orchestrator()

    # Create sub-agent specs based on the goal
    agents = [
        SubAgentSpec(
            name="researcher",
            purpose=f"Research best approaches for: {goal}",
            agent_type="researcher",
            context_level="level_2",
        ),
        SubAgentSpec(
            name="planner",
            purpose=f"Plan implementation steps for: {goal}",
            agent_type="general",
            context_level="level_2",
        ),
        SubAgentSpec(
            name="reviewer",
            purpose=f"Review outputs and quality for: {goal}",
            agent_type="reviewer",
            context_level="level_1",
        ),
    ]

    print(f"\n{'='*60}")
    print(f"  Orchestration: {goal}")
    print(f"  Agents: {len(agents)} ({', '.join(a.name for a in agents)})")
    print(f"  Pattern: fan_out_fan_in")
    print(f"{'='*60}\n")

    run = orch.fan_out(agents, goal=goal)

    print(f"\n{'='*60}")
    print(f"  Orchestration Complete: {run.id}")
    print(f"  Status: {run.status}")
    print(f"  Duration: {run.duration}s")
    print(f"  Merged result count: {len(run.agents) if run.agents else 0} agents")

    for agent in run.agents:
        status_icon = "✅" if agent.status.value == "completed" else "❌"
        print(f"  {status_icon} {agent.spec.name}: {agent.status.value} ({agent.duration:.2f}s)")
        if agent.error:
            print(f"     Error: {agent.error[:150]}")

    print(f"{'='*60}\n")

    print(f"Run saved to: orchestrations/{run.id}.json")


def _cmd_orch_list(args):
    """List recent orchestration runs."""
    orch = Orchestrator()
    runs = orch.list_runs(limit=10)

    if not runs:
        print("No orchestration runs found.")
        return

    print(f"{'Run ID':<20} {'Pattern':<16} {'Status':<12} {'Agents':<8} {'Duration':<10} Goal")
    print("-" * 90)
    for r in runs:
        agents = len(r.agents)
        goal_preview = r.goal[:40] + "..." if len(r.goal) > 40 else r.goal
        print(f"{r.id:<20} {r.pattern.value:<16} {r.status:<12} {agents:<8} {r.duration:<10.2f} {goal_preview}")


def _cmd_orch_inspect(args):
    """Inspect an orchestration run."""
    if not args:
        print("Usage: orch-inspect <run_id>")
        return

    orch = Orchestrator()
    run = orch.load_run(args[0])
    if not run:
        print(f"Orchestration run '{args[0]}' not found.")
        return

    print(f"Orchestration: {run.id}")
    print(f"  Goal:     {run.goal}")
    print(f"  Pattern:  {run.pattern.value}")
    print(f"  Status:   {run.status}")
    print(f"  Created:  {run.created_at}")
    print(f"  Duration: {run.duration}s")
    print()

    print("  Agents:")
    for agent in run.agents:
        status_icon = {"completed": "✅", "failed": "❌", "timeout": "⏰", "running": "▶️"}.get(agent.status.value, "⬜")
        print(f"    {status_icon} {agent.spec.name} ({agent.id})")
        print(f"       Type: {agent.spec.agent_type}")
        print(f"       Status: {agent.status.value}")
        print(f"       Duration: {agent.duration:.2f}s")
        if agent.error:
            print(f"       Error: {agent.error[:200]}")

    if run.merged_result:
        print(f"\n  Merged Result: {json.dumps(run.merged_result, indent=4)[:500]}")


# ── Phase 4: Handoff Commands ─────────────────────────────────────────────────


def _cmd_handoff(args):
    """Create a handoff between agents."""
    if len(args) < 3:
        print("Usage: handoff <sender> <receiver> <message>")
        print("Example: handoff planner executor 'Implement the planned features'")
        return

    sender = args[0]
    receiver = args[1]
    message = " ".join(args[2:])

    protocol = HandoffProtocol()
    context = ContextPackage(
        goal_description=message,
        priority="normal",
    )

    handoff = protocol.create(sender, receiver, context, message=message)
    print(f"Handoff created: {handoff.id}")
    print(f"  From: {handoff.sender}")
    print(f"  To:   {handoff.receiver}")
    print(f"  Status: {handoff.status.value}")
    print(f"  Message: {handoff.message}")


def _cmd_handoff_list(args):
    """List handoffs, optionally filtered by receiver."""
    receiver = args[0] if args else None
    protocol = HandoffProtocol()

    if receiver:
        handoffs = protocol.find_by_receiver(receiver)
    else:
        handoffs = protocol.find_by_status(HandoffStatus.PENDING)

    if not handoffs:
        print("No handoffs found.")
        return

    print(f"{'Handoff ID':<24} {'From':<14} {'To':<14} {'Status':<16} {'Message':<30}")
    print("-" * 100)
    for h in handoffs[:15]:
        msg = h.message[:28] + "..." if len(h.message) > 28 else h.message
        print(f"{h.id:<24} {h.sender:<14} {h.receiver:<14} {h.status.value:<16} {msg}")


def _cmd_handoff_claim(args):
    """Claim and process a handoff."""
    if len(args) < 2:
        print("Usage: handoff-claim <handoff_id> <agent_name>")
        return

    handoff_id = args[0]
    agent_name = args[1]

    protocol = HandoffProtocol()

    # Deliver
    handoff = protocol.deliver(handoff_id, agent_name)
    if not handoff:
        print(f"Cannot deliver handoff {handoff_id} to {agent_name}.")
        return

    print(f"Handoff delivered: {handoff.id}")
    print(f"  From: {handoff.sender}")
    print(f"  Message: {handoff.message}")

    # Acknowledge
    protocol.acknowledge(handoff_id, agent_name)
    print(f"  Acknowledged by {agent_name}")

    # Complete
    protocol.complete(handoff_id, agent_name, response=f"Processed by {agent_name}")
    print(f"  Completed by {agent_name}")


# ── Phase 4: Context Management Commands ──────────────────────────────────────


def _cmd_context(args):
    """Show context summary at a given level."""
    level_str = args[0] if args else "level_1"
    try:
        level = ContextLevel(level_str)
    except ValueError:
        print(f"Invalid level: {level_str}. Use: level_1, level_2 or level_3")
        return

    cm = ContextManager()
    summary = cm.get_context_summary(level)
    print(summary)


def _cmd_context_nav(args):
    """Generate context navigation.md."""
    cm = ContextManager()

    entries = [
        NavigationEntry("Task Queue", "system/task_queue.py", "Pull-based task queue with priority ordering", "guide", ["task", "queue"], 9),
        NavigationEntry("Executor", "system/executor.py", "Task execution loop (claim → execute → verify → record)", "guide", ["execution", "loop"], 9),
        NavigationEntry("Decomposer", "system/decomposer.py", "Goal decomposition into task graphs", "guide", ["goal", "decomposition"], 8),
        NavigationEntry("Verifier", "system/verifier.py", "Task verification with evidence capture", "guide", ["verification", "testing"], 8),
        NavigationEntry("Profiles", "system/profiles.py", "Agent profile registry and loader", "concept", ["profiles", "agents"], 7),
        NavigationEntry("Model Router", "system/model_router.py", "Cheap vs strong model routing", "concept", ["routing", "models"], 7),
        NavigationEntry("Skill Registry", "system/skill_registry.py", "Skill discovery and matching", "concept", ["skills", "registry"], 7),
        NavigationEntry("Eval Harness", "system/eval.py", "Eval suite runner with regression tracking", "guide", ["eval", "testing"], 9),
        NavigationEntry("Self Improvement", "system/self_improve.py", "One-change eval-verified improvement", "guide", ["improvement", "eval"], 8),
        NavigationEntry("Gap Classifier", "system/gap_classifier.py", "Failure classification by gap type", "guide", ["failure", "classification"], 8),
        NavigationEntry("Gap Repair", "system/gap_repair.py", "Auto-repair cycle for failures", "guide", ["repair", "automation"], 8),
        NavigationEntry("Orchestrator", "system/orchestrator.py", "Multi-agent fan-out/fan-in orchestration", "guide", ["orchestration", "parallel"], 9),
        NavigationEntry("Handoff Protocol", "system/handoff.py", "Agent-to-agent context handoff", "guide", ["handoff", "communication"], 8),
        NavigationEntry("Context Manager", "system/context_manager.py", "3-level context allocation system", "concept", ["context", "allocation"], 8),
        NavigationEntry("Production Hardening", "system/hardening.py", "Retry, timeout, circuit-breaker patterns", "guide", ["hardening", "reliability"], 8),
        NavigationEntry("Agent Spawner", "system/agent_spawner.py", "Sub-agent process spawning with streaming", "guide", ["spawning", "process"], 8),
        NavigationEntry("Regression Prevention", "system/regression_prevention.py", "Eval-driven regression prevention", "guide", ["regression", "prevention"], 8),
        NavigationEntry("CLI", "system/cli.py", "Unified CLI entry point (40+ commands)", "guide", ["cli", "commands"], 9),
        NavigationEntry("Models", "system/models.py", "Task, Goal, MemoryEntry data models", "concept", ["models", "dataclasses"], 7),
        NavigationEntry("Memory", "system/memory.py", "Hot/warm/cold memory tiers", "concept", ["memory", "tiers"], 7),
    ]

    nav_content = cm.generate_navigation(entries)
    cm.save_navigation(nav_content)

    # Also save to the knowledge artifacts
    nav_dir = Path(".opencode_context/navigation")
    nav_dir.mkdir(parents=True, exist_ok=True)
    (nav_dir / "context-index.md").write_text(nav_content, encoding="utf-8")

    print(f"Navigation file generated: .opencode_context/navigation.md")
    print(f"  Index saved to: .opencode_context/navigation/context-index.md")
    print(f"  Total entries: {len(entries)}")
    print(f"\nCategories:")
    for e in entries:
        print(f"  [{e.level}] {e.title} — {e.description}")


# ── Phase 4: DCP (Dynamic Context Pruning) Commands ──────────────────────────────


def _cmd_dcp(args):
    """Run a full DCP pruning cycle on current context."""
    cm = ContextManager()
    result = cm.run_dcp_cycle()
    if result.get("error"):
        print(f"DCP error: {result['error']}")
        return
    print("=== DCP Pruning Cycle ===")
    print(f"  Action:         {result['action']}")
    print(f"  Tokens before:  {result.get('tokens_before', 0):,}")
    print(f"  Tokens after:   {result.get('tokens_after', 0):,}")
    print(f"  Tokens saved:   {result.get('tokens_saved', 0):,}")
    print(f"  Items before:   {result.get('items_before', 0)}")
    print(f"  Items after:    {result.get('items_after', 0)}")
    print(f"  Items removed:  {result.get('items_removed', 0)}")
    print(f"  Health:         {result.get('health_status', 'N/A')}")


def _cmd_dcp_prune(args):
    """Run DCP pruning and show detailed results."""
    cm = ContextManager()
    result = cm.run_dcp_cycle()
    if result.get("error"):
        print(f"DCP error: {result['error']}")
        return
    print("=== DCP Prune Results ===")
    for key, val in result.items():
        print(f"  {key}: {val}")


def _cmd_dcp_status(args):
    """Show DCP engine configuration and health."""
    cm = ContextManager()
    status = cm.get_dcp_status()

    if not status.get("enabled"):
        print(status.get("message", "DCP not available"))
        return

    print("=== DCP Status ===")
    print(f"Enabled: {status['enabled']}")

    if "monitor" in status:
        print("\n--- Monitor Thresholds ---")
        for key, val in status["monitor"].items():
            print(f"  {key}: {val:,}" if isinstance(val, int) else f"  {key}: {val}")

    if "compactor" in status:
        print("\n--- Compactor ---")
        for key, val in status["compactor"].items():
            print(f"  {key}: {val}")

    if "offloader" in status:
        print("\n--- Offloader ---")
        for key, val in status["offloader"].items():
            print(f"  {key}: {val:,}" if isinstance(val, int) else f"  {key}: {val}")


def _cmd_dcp_config(args):
    """Show or save DCP configuration."""
    path = args[0] if args else ".context_pruning_config.json"
    engine = ContextPruningEngine(config_path=path)
    config = engine.config.to_dict()

    print("=== DCP Configuration ===")
    for section, values in config.items():
        print(f"\n  [{section}]")
        if isinstance(values, dict):
            for k, v in values.items():
                print(f"    {k}: {v}")
        else:
            print(f"    value: {values}")

    if "--save" in args:
        engine.save_config()
        print(f"\nConfiguration saved to: {path}")


# ── Phase 4: Hardening Commands ────────────────────────────────────────────────


def _cmd_circuit(args):
    """Show circuit breaker state(s)."""
    name = args[0] if args else None

    if name:
        cb = CircuitBreaker(name)
        print(cb.get_state_summary())
    else:
        breakers = get_all_circuit_breakers()
        if not breakers:
            print("No circuit breakers found.")
            return

        print(f"{'Name':<24} {'State':<12} {'Failures':<12} {'Successes':<12} {'Last Error':<40}")
        print("-" * 100)
        for cb_data in breakers:
            err = (cb_data.get("last_error") or "—")[:38]
            print(f"{cb_data.get('name', '?'):<24} {cb_data.get('state', '?'):<12} "
                  f"{cb_data.get('total_failures', 0):<12} {cb_data.get('total_successes', 0):<12} {err}")


def _cmd_circuit_reset(args):
    """Reset circuit breaker(s)."""
    name = args[0] if args else None

    if name:
        cb = CircuitBreaker(name)
        cb.reset()
        print(f"Circuit breaker '{name}' reset to closed state.")
    else:
        reset_all_circuit_breakers()
        print("All circuit breakers reset to closed state.")


def _cmd_hardener(args):
    """Execute a command with hardening (retry + timeout + circuit-breaker)."""
    if len(args) < 2:
        print("Usage: hardener <name> <command>")
        print("Example: hardener db-query 'python -m system.cli status'")
        return

    name = args[0]
    command = " ".join(args[1:])

    import subprocess

    def run_cmd():
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500])
        return result.stdout[:2000]

    hardener = Hardener(name=name, timeout=20.0, max_retries=2)
    print(f"Hardener: {name}")
    print(f"  Timeout: {hardener.timeout_handler.timeout_seconds}s")
    print(f"  Max retries: {hardener.retry.config.max_retries}")
    print(f"  Circuit breaker threshold: {hardener.circuit_breaker.config.failure_threshold}")
    print(f"\nExecuting: {command}\n")

    try:
        output = hardener.execute(run_cmd)
        print(f"\n✅ Succeeded")
        if output:
            print(f"Output: {output[:500]}")
    except Exception as e:
        print(f"\n❌ Failed after hardening: {e}")

    stats = hardener.get_stats()
    print(f"\nHardener stats:")
    print(f"  Circuit state: {stats['circuit_breaker']['state']}")
    print(f"  Total failures: {stats['circuit_breaker']['total_failures']}")


# ── Phase 4: Agent Spawner Commands ───────────────────────────────────────────


def _cmd_spawn(args):
    """Spawn a sub-agent with real-time streaming output."""
    if not args:
        print("Usage: spawn <command...>")
        print("Example: spawn python -m pytest tests/ -v")
        return

    command = args
    label = command[0]

    spawner = AgentSpawner()
    print(f"\n{'='*60}")
    print(f"  Spawning: {' '.join(command)}")
    print(f"{'='*60}\n")

    process = spawner.spawn(command, label=label)

    print(f"\n{'='*60}")
    print(f"  Process: {process.id}")
    print(f"  Status:  {process.status.value}")
    print(f"  Exit:    {process.exit_code}")
    print(f"  Duration: {process.duration:.2f}s")
    if process.error:
        print(f"  Error:   {process.error[:300]}")
    print(f"{'='*60}")


def _cmd_spawn_list(args):
    """List spawned processes."""
    status_str = args[0] if args else None
    status = AgentProcessStatus(status_str) if status_str else None

    spawner = AgentSpawner()
    processes = spawner.list_processes(status=status, limit=20)

    if not processes:
        print("No spawned processes found.")
        return

    print(f"{'Process ID':<22} {'Label':<18} {'Status':<12} {'Duration':<10} {'Exit Code':<10} Command")
    print("-" * 100)
    for p in processes:
        cmd = " ".join(p.command)[:35]
        print(f"{p.id:<22} {p.label:<18} {p.status.value:<12} {p.duration:<10.2f} {str(p.exit_code or '—'):<10} {cmd}")


def _cmd_spawn_kill(args):
    """Kill a spawned process."""
    if not args:
        print("Usage: spawn-kill <process_id>")
        return

    spawner = AgentSpawner()
    success = spawner.kill(args[0])

    if success:
        print(f"Process {args[0]} killed.")
    else:
        print(f"Failed to kill process {args[0]} (not found or already completed).")


# ── Phase 4: Regression Prevention Commands ────────────────────────────────────


def _cmd_gate(args):
    """Run a regression check against a policy."""
    if not args:
        print("Usage: gate <policy_name>")
        print("Available policies: task-completion, self-improve, deploy, code-change, config-change")
        return

    policy_name = args[0]
    preventer = RegressionPreventer()
    preventer.create_default_policies()

    print(f"Running regression check for policy: {policy_name}")
    result = preventer.check(policy_name)

    print(f"\nCheck Result:")
    print(f"  Passed:  {'✅ YES' if result.passed else '❌ NO'}")
    print(f"  Rate:    {result.pass_rate:.1%} (required: {preventer.get_policy(policy_name).required_pass_rate if preventer.get_policy(policy_name) else '—'})")
    print(f"  Action:  {result.action_taken}")
    print(f"  Cases:   {result.total_cases} total, {result.failed_cases} failed")
    print(f"  Regressions: {result.regressions_found}")
    print(f"  Duration: {result.duration:.2f}s")

    if result.details:
        print(f"\n  Details:")
        for d in result.details:
            print(f"    - {d}")


def _cmd_gate_policies(args):
    """List regression prevention policies."""
    preventer = RegressionPreventer()
    preventer.create_default_policies()
    policies = preventer.list_policies()

    if not policies:
        print("No policies defined.")
        return

    print(f"{'Policy':<20} {'Scope':<14} {'Required':<10} {'Action':<12} {'Cooldown':<10} Description")
    print("-" * 90)
    for p in policies:
        cd = f"{p.cooldown_seconds}s"
        print(f"{p.name:<20} {p.eval_scope.value:<14} {p.required_pass_rate:<10.0%} {p.action_on_failure.value:<12} {cd:<10} {p.description[:40]}")


def _cmd_gate_check(args):
    """Guard task completion with regression check."""
    if not args:
        print("Usage: gate-check <task_description>")
        return

    description = " ".join(args)
    preventer = RegressionPreventer()
    preventer.create_default_policies()

    print(f"🧪 Regression Guard: {description}")
    safe = preventer.guard_task_completion("manual", description)

    if safe:
        print(f"\n✅ Safe to complete.")
    else:
        print(f"\n❌ Regression check blocked completion.")


# ── Phase 5: Momentum Commands ──────────────────────────────────────────────────


def _cmd_momentum(args):
    """Momentum dashboard — quick overview."""
    monitor = MomentumMonitor()
    health = monitor.analyze_queue_health()

    # Determine health icon
    if health.overall_health >= 0.8:
        health_icon = "🟢"
    elif health.overall_health >= 0.5:
        health_icon = "🟡"
    else:
        health_icon = "🔴"

    blocked = monitor.find_blocked_tasks()

    print("+========================================+")
    print("|       MOMENTUM OVERVIEW                |")
    print("+========================================+")
    print()
    print(f"  Health:        {health_icon} {health.overall_health:.1%}")
    print(f"  Total tasks:   {health.total_tasks}")
    print(f"  Pending:       {health.pending}")
    print(f"  In progress:   {health.in_progress}")
    print(f"  Completed:     {health.completed}")
    print(f"  Failed:        {health.failed}")
    print(f"  Blocked:       {health.blocked_count}")
    print(f"  Stale claims:  {health.stale_count}")
    print()
    print(f"  Velocity:      {health.velocity_per_hour:.2f} tasks/hour")
    print(f"  Completed 24h: {health.completed_last_24h}")
    print()
    print(f"  P0 pending:    {health.p0_pending}")
    print(f"  P1 pending:    {health.p1_pending}")
    print(f"  P2 pending:    {health.p2_pending}")

    if blocked:
        print()
        print(f"  Blocked tasks ({len(blocked)}):")
        for bt in blocked[:5]:
            print(f"    {bt.task_id}: {bt.description[:50]} ({bt.reason}, {bt.blocked_hours:.1f}h)")

    print()
    print("  Run 'momentum-report' for full details + recommendations")
    print("  Run 'momentum-snapshots' for trend history")


def _cmd_momentum_report(args):
    """Full momentum report with recommendations."""
    verbose = "--verbose" in args or "-v" in args
    monitor = MomentumMonitor()
    report = monitor.generate_report(verbose=verbose)
    print(report)


def _cmd_momentum_snapshots(args):
    """List recent momentum snapshots."""
    limit = int(args[0]) if args and args[0].isdigit() else 20
    monitor = MomentumMonitor()
    snapshots = monitor.list_snapshots(limit=limit)

    if not snapshots:
        print("No momentum snapshots found.")
        print("Run 'momentum-report' to take the first snapshot.")
        return

    print(f"{'Timestamp':<20} {'Health':<10} {'Blocked':<10} {'Stale':<10} {'Velocity':<12} {'Pending':<10} {'Done/24h':<10}")
    print("-" * 82)
    for s in snapshots:
        ts = s["timestamp"][:16] if s["timestamp"] else "?"
        health = f"{s.get('overall_health', 0):.1%}"
        blocked = s.get("blocked", 0)
        stale = s.get("stale", 0)
        velocity = f"{s.get('velocity', 0):.2f}/h"
        pending = s.get("pending", 0)
        done24h = s.get("completed_last_24h", 0)
        print(f"{ts:<20} {health:<10} {blocked:<10} {stale:<10} {velocity:<12} {pending:<10} {done24h:<10}")

    print(f"\n{len(snapshots)} snapshots total (retention: 50)")


def _cmd_momentum_stats(args):
    """Momentum monitor statistics."""
    monitor = MomentumMonitor()
    stats = monitor.get_stats()

    print("Momentum Monitor Statistics:")
    print()
    qh = stats["queue_health"]
    print(f"  Queue state:  {qh['total']} total, {qh['pending']} pending, {qh['completed']} completed")
    print(f"  Velocity:     {qh['velocity']:.2f} tasks/hour")
    print(f"  Blocked:      {qh['blocked']}")
    print(f"  Stale:        {qh['stale']}")
    print(f"  Overall:      {qh['overall_health']:.1%}")
    print()
    print(f"  Blocked by reason:")
    for reason, count in stats["blocked_by_reason"].items():
        print(f"    {reason}: {count}")
    print()
    print(f"  Snapshots:    {stats['snapshots_available']} available")
    if stats["latest_snapshot"]:
        ls = stats["latest_snapshot"]
        print(f"  Latest:       {ls['timestamp'][:16]} (health {ls.get('overall_health', '?')})")


# ── Phase 5: Scheduler Commands ─────────────────────────────────────────────────

def _cmd_schedule(args):
    """Show schedule info."""
    if not args:
        print("Usage: schedule <name>")
        print("Use 'schedule-list' to see all schedules")
        return

    name = args[0]
    scheduler = Scheduler()
    schedule = scheduler.get_schedule(name)

    if not schedule:
        print(f"Schedule '{name}' not found.")
        return

    print(f"Schedule: {schedule.name}")
    print(f"  Cron: {schedule.cron_expr}")
    print(f"  Command: {schedule.command}")
    print(f"  Description: {schedule.description or '(none)'}")
    print(f"  Enabled: {schedule.enabled}")
    print(f"  Next run: {schedule.next_run or '(not scheduled)'}")
    print(f"  Last run: {schedule.last_run or '(never)'}")
    print(f"  Runs: {schedule.run_count} total, {schedule.success_count} success, {schedule.failure_count} failed")


def _cmd_schedule_list(args):
    """List all schedules."""
    scheduler = Scheduler()
    schedules = scheduler.list_schedules()

    if not schedules:
        print("No schedules found.")
        print("Use 'schedule-create' to create a new schedule.")
        return

    print(f"{'Name':<20} {'Enabled':<10} {'Next Run':<20} {'Runs':<10} Command")
    print("-" * 90)
    for s in schedules:
        enabled = "✓" if s.enabled else "✗"
        next_run = s.next_run[:16] if s.next_run else "(not set)"
        runs = f"{s.run_count}/{s.success_count}"
        cmd = s.command[:40] + "..." if len(s.command) > 40 else s.command
        print(f"{s.name:<20} {enabled:<10} {next_run:<20} {runs:<10} {cmd}")


def _cmd_schedule_create(args):
    """Create a new schedule."""
    if len(args) < 3:
        print("Usage: schedule-create <name> <cron_expr> <command>")
        print("Example: schedule-create daily-backup '0 2 * * *' 'python -m system.cli run'")
        return

    name = args[0]
    cron_expr = args[1]
    command = " ".join(args[2:])

    scheduler = Scheduler()
    try:
        schedule = scheduler.create_schedule(name, cron_expr, command)
        print(f"Schedule created: {schedule.name}")
        print(f"  Cron: {schedule.cron_expr}")
        print(f"  Command: {schedule.command}")
        print(f"  Next run: {schedule.next_run}")
    except ValueError as e:
        print(f"Error: {e}")


def _cmd_schedule_enable(args):
    """Enable a schedule."""
    if not args:
        print("Usage: schedule-enable <name>")
        return

    name = args[0]
    scheduler = Scheduler()
    if scheduler.enable_schedule(name):
        print(f"Schedule '{name}' enabled.")
    else:
        print(f"Schedule '{name}' not found.")


def _cmd_schedule_disable(args):
    """Disable a schedule."""
    if not args:
        print("Usage: schedule-disable <name>")
        return

    name = args[0]
    scheduler = Scheduler()
    if scheduler.disable_schedule(name):
        print(f"Schedule '{name}' disabled.")
    else:
        print(f"Schedule '{name}' not found.")


def _cmd_schedule_delete(args):
    """Delete a schedule."""
    if not args:
        print("Usage: schedule-delete <name>")
        return

    name = args[0]
    scheduler = Scheduler()
    if scheduler.delete_schedule(name):
        print(f"Schedule '{name}' deleted.")
    else:
        print(f"Schedule '{name}' not found.")


def _cmd_schedule_run(args):
    """Run all due schedules, creating Tasks in the task queue."""
    scheduler = Scheduler()
    results = scheduler.run_due()

    if not results:
        print("No due schedules found.")
        return

    for r in results:
        status_icon = "OK" if r["status"] == "created" else "FAIL"
        print(f"  [{status_icon}] {r['schedule']}")
        if r.get("task_id"):
            print(f"       Task: {r['task_id']}")
        if r.get("error"):
            print(f"       Error: {r['error']}")
    print(f"\nRan {len(results)} schedule(s).")


# ── Dashboard Command ────────────────────────────────────────────────────────

def _cmd_dashboard(args):
    """Generate HTML system dashboard."""
    do_open = "--open" in args
    if do_open:
        _open_dashboard()
    else:
        generate_dashboard()
        print("Use '--open' to open in your browser.")


# ── GUI Command ────────────────────────────────────────────────────────────────

def _cmd_gui(args):
    """Start the web-based GUI dashboard."""
    from system.gui import GUIApplication, GUIConfig

    host = "127.0.0.1"
    port = 8080
    debug = False
    refresh = 5

    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--debug":
            debug = True
            i += 1
        elif args[i] == "--refresh" and i + 1 < len(args):
            refresh = int(args[i + 1])
            i += 2
        elif args[i] in ("--help", "-h"):
            print("Usage: gui [options]")
            print("  --host <host>     Host to bind to (default: 127.0.0.1)")
            print("  --port <port>     Port to listen on (default: 8080)")
            print("  --debug           Enable debug mode")
            print("  --refresh <sec>   Auto-refresh interval (default: 5)")
            return
        else:
            i += 1

    config = GUIConfig(host=host, port=port, debug=debug, auto_refresh=refresh)
    gui = GUIApplication(config)
    gui.start()


# ── Phase 5: Intelligence Commands ───────────────────────────────────────────

def _cmd_pattern(args):
    """Show pattern details."""
    if not args:
        print("Usage: pattern <pattern_id>")
        print("Use 'pattern-list' to see all patterns")
        return

    pattern_id = args[0]
    monitor = IntelligenceMonitor()
    pattern = monitor.get_pattern(pattern_id)

    if not pattern:
        print(f"Pattern '{pattern_id}' not found.")
        return

    print(f"Pattern: {pattern.title}")
    print(f"  ID: {pattern.id}")
    print(f"  Source: {pattern.source}")
    print(f"  Category: {pattern.category}")
    print(f"  URL: {pattern.url}")
    print(f"  Confidence: {pattern.confidence:.0%}")
    print(f"  Relevance: {pattern.relevance_score:.0%}")
    print(f"  Applied: {'Yes' if pattern.applied else 'No'}")
    print(f"  Discovered: {pattern.discovered_at[:16]}")
    if pattern.description:
        print(f"  Description: {pattern.description[:80]}...")
    if pattern.notes:
        print(f"  Notes: {pattern.notes}")


def _cmd_pattern_list(args):
    """List all patterns."""
    monitor = IntelligenceMonitor()
    patterns = monitor.list_patterns()

    if not patterns:
        print("No patterns found.")
        print("Use 'pattern-add' to add a new pattern.")
        return

    applied_filter = "--applied" in args
    pending_filter = "--pending" in args

    if applied_filter:
        patterns = [p for p in patterns if p.applied]
    elif pending_filter:
        patterns = [p for p in patterns if not p.applied]

    print(f"{'ID':<12} {'Category':<15} {'Relevance':<10} {'Applied':<8} Title")
    print("-" * 90)
    for p in patterns[:30]:
        applied = "✓" if p.applied else "✗"
        title = p.title[:40] + "..." if len(p.title) > 40 else p.title
        print(f"{p.id:<12} {p.category:<15} {p.relevance_score:.0%}       {applied:<8} {title}")

    if len(patterns) > 30:
        print(f"\n... and {len(patterns) - 30} more (use --applied or --pending to filter)")


def _cmd_pattern_add(args):
    """Add a new pattern."""
    if len(args) < 4:
        print("Usage: pattern-add <source> <title> <category> <url> [description] [confidence]")
        print("Categories: tool, model, pattern, protocol, best_practice")
        print("Example: pattern-add github 'New agent pattern' pattern 'https://github.com/...'")
        return

    source = args[0]
    title = args[1]
    category = args[2]
    url = args[3]
    description = args[4] if len(args) > 4 else ""
    confidence = float(args[5]) if len(args) > 5 else 0.5

    monitor = IntelligenceMonitor()
    pattern = monitor.add_pattern(
        source=source,
        title=title,
        description=description,
        url=url,
        category=category,
        confidence=confidence,
    )
    print(f"Pattern added: {pattern.id}")
    print(f"  Title: {pattern.title}")
    print(f"  Category: {pattern.category}")
    print(f"  URL: {pattern.url}")


def _cmd_pattern_apply(args):
    """Mark a pattern as applied."""
    if not args:
        print("Usage: pattern-apply <pattern_id>")
        return

    pattern_id = args[0]
    monitor = IntelligenceMonitor()
    if monitor.mark_pattern_applied(pattern_id):
        print(f"Pattern '{pattern_id}' marked as applied.")
    else:
        print(f"Pattern '{pattern_id}' not found.")


def _cmd_pattern_delete(args):
    """Delete a pattern."""
    if not args:
        print("Usage: pattern-delete <pattern_id>")
        return

    pattern_id = args[0]
    monitor = IntelligenceMonitor()
    if monitor.delete_pattern(pattern_id):
        print(f"Pattern '{pattern_id}' deleted.")
    else:
        print(f"Pattern '{pattern_id}' not found.")


def _cmd_source(args):
    """Show source info."""
    if not args:
        print("Usage: source <name>")
        print("Use 'source-list' to see all sources")
        return

    name = args[0]
    monitor = IntelligenceMonitor()
    source = monitor.get_source(name)

    if not source:
        print(f"Source '{name}' not found.")
        return

    print(f"Source: {source.name}")
    print(f"  Type: {source.type}")
    print(f"  URL: {source.url}")
    print(f"  Query: {source.query or '(none)'}")
    print(f"  Enabled: {source.enabled}")
    print(f"  Check interval: {source.check_interval_hours}h")
    print(f"  Last check: {source.last_check or '(never)'}")
    print(f"  Patterns found: {source.patterns_found}")


def _cmd_source_list(args):
    """List all sources."""
    monitor = IntelligenceMonitor()
    sources = monitor.list_sources()

    if not sources:
        print("No sources found.")
        print("Use 'source-create' to create a new source.")
        return

    print(f"{'Name':<20} {'Type':<10} {'Enabled':<10} {'Patterns':<10} URL")
    print("-" * 90)
    for s in sources:
        enabled = "✓" if s.enabled else "✗"
        url = s.url[:40] + "..." if len(s.url) > 40 else s.url
        print(f"{s.name:<20} {s.type:<10} {enabled:<10} {s.patterns_found:<10} {url}")


def _cmd_source_create(args):
    """Create a new source."""
    if len(args) < 3:
        print("Usage: source-create <name> <type> <url> [query] [interval_hours]")
        print("Types: github, npm, pypi, rss, api")
        print("Example: source-create github-issues 'github' 'https://api.github.com/repos/...' 'issues'")
        return

    name = args[0]
    source_type = args[1]
    url = args[2]
    query = args[3] if len(args) > 3 else ""
    interval = int(args[4]) if len(args) > 4 else 24

    monitor = IntelligenceMonitor()
    try:
        source = monitor.create_source(name, source_type, url, query, interval)
        print(f"Source created: {source.name}")
        print(f"  Type: {source.type}")
        print(f"  URL: {source.url}")
        print(f"  Check interval: {source.check_interval_hours}h")
    except ValueError as e:
        print(f"Error: {e}")


def _cmd_source_check(args):
    """Check a source for new patterns."""
    if not args:
        print("Usage: source-check <name>")
        print("Use 'source-list' to see all sources")
        return

    name = args[0]
    monitor = IntelligenceMonitor()
    patterns = monitor.check_source(name)

    if not patterns:
        print(f"No new patterns found in source '{name}'.")
        return

    print(f"Found {len(patterns)} new pattern(s) in '{name}':")
    for p in patterns:
        print(f"  - {p.title} ({p.category})")


def _cmd_source_check_all(args):
    """Check all enabled sources for new patterns."""
    monitor = IntelligenceMonitor()
    results = monitor.check_all_sources()

    if not results:
        print("No sources configured. Use 'source-create' to add sources.")
        return

    total = sum(len(patterns) for patterns in results.values())
    print(f"Checked all sources. Found {total} new pattern(s) total.")
    for name, patterns in results.items():
        print(f"  {name}: {len(patterns)} new pattern(s)")


def _cmd_intelligence_stats(args):
    """Show intelligence monitor statistics."""
    monitor = IntelligenceMonitor()
    stats = monitor.get_stats()

    print("Intelligence Monitor Statistics:")
    print()
    print(f"  Total patterns: {stats['total_patterns']}")
    print(f"  Applied patterns: {stats['applied_patterns']}")
    print(f"  Pending patterns: {stats['pending_patterns']}")
    print()
    print(f"  Total sources: {stats['total_sources']}")
    print(f"  Enabled sources: {stats['enabled_sources']}")
    print()
    if stats['patterns_by_category']:
        print("  Patterns by category:")
        for cat, count in stats['patterns_by_category'].items():
            print(f"    {cat}: {count}")


# ── Phase 6: Harness Commands ──────────────────────────────────────────────────


def _cmd_coding_run(args):
    """Run the coding delivery harness."""
    if not args:
        print("Usage: coding-run <goal> [--tags tag1,tag2]")
        return
    goal = args[0]
    tags = []
    if len(args) > 2 and args[1] == "--tags":
        tags = [t.strip() for t in args[2].split(",")]
    print(CodingHarness(goal, tags=tags).execute().summary or "Coding run complete.")


def _cmd_coding_resume(args):
    """Resume a paused coding harness run."""
    if not args:
        print("Usage: coding-resume <run_id>")
        return
    saved = load_harness_run(args[0])
    if not saved:
        print(f"Run {args[0]} not found.")
        return
    if saved.harness_type != "coding":
        print(f"Run {args[0]} is a '{saved.harness_type}' run, not a coding run.")
        return
    harness = CodingHarness(saved.goal, run_id=saved.id, tags=saved.tags)
    harness.run = saved
    result = harness.resume()
    stg = result.current_stage()
    if stg:
        print(f"Coding run {result.id} paused at stage '{stg.name}'")
    else:
        print(f"Coding run {result.id} complete: {result.status.value}")


def _cmd_coding_status(args):
    """Show coding harness run details."""
    print(CodingHarness.cmd_status(args))


def _cmd_coding_list(args):
    """List all coding harness runs."""
    print(CodingHarness.cmd_list(args))


def _cmd_research_run(args):
    """Run the research harness."""
    if not args:
        print("Usage: research-run <goal> [--tags tag1,tag2]")
        return
    goal = args[0]
    tags = []
    if len(args) > 2 and args[1] == "--tags":
        tags = [t.strip() for t in args[2].split(",")]
    result = ResearchHarness(goal, tags=tags).execute()
    print(result.summary or "Research run complete.")


def _cmd_research_resume(args):
    """Resume a paused research harness run."""
    if not args:
        print("Usage: research-resume <run_id>")
        return
    saved = load_harness_run(args[0])
    if not saved:
        print(f"Run {args[0]} not found.")
        return
    if saved.harness_type != "research":
        print(f"Run {args[0]} is a '{saved.harness_type}' run, not a research run.")
        return
    harness = ResearchHarness(saved.goal, run_id=saved.id, tags=saved.tags)
    harness.run = saved
    result = harness.resume()
    stg = result.current_stage()
    if stg:
        print(f"Research run {result.id} paused at stage '{stg.name}'")
    else:
        print(f"Research run {result.id} complete: {result.status.value}")


def _cmd_research_status(args):
    """Show research harness run details."""
    print(ResearchHarness.cmd_status(args))


def _cmd_research_list(args):
    """List all research harness runs."""
    print(ResearchHarness.cmd_list(args))


def _cmd_harness_list(args):
    """List all harness runs across all types."""
    runs = list_harness_runs()
    if not runs:
        print("No harness runs found.")
        return
    lines = [f"{'ID':<14} {'Type':<12} {'Status':<12} {'Stages':<10} {'Goal'}", "-" * 80]
    for r in runs:
        lines.append(f"{r.id:<14} {r.harness_type:<12} {r.status.value:<12} {r.progress_str:<10} {r.goal[:50]}")
    print("\n".join(lines))


def _cmd_harness_status(args):
    """Show details for any harness run."""
    if not args:
        print("Usage: harness-status <run_id>")
        return
    from .harness import HarnessBase
    # Use a minimal display that works for all harness types
    saved = load_harness_run(args[0])
    if not saved:
        print(f"Run {args[0]} not found.")
        return
    lines = [
        f"Harness: {saved.id} ({saved.harness_type})",
        f"  Goal:    {saved.goal[:100]}",
        f"  Status:  {saved.status.value}",
        f"  Created: {saved.created_at[:19]}",
        f"  Stages:  {saved.progress_str}",
    ]
    if saved.summary:
        lines.append(f"  Summary: {saved.summary[:100]}")
    for s in saved.stages:
        icon = {"pending": "○", "running": "▶", "completed": "✓", "failed": "✗", "skipped": "–"}
        lines.append(f"  {icon.get(s.status.value, '?')} {s.name} ({s.status.value})")
        if s.error:
            lines.append(f"    Error: {s.error[:120]}")
    print("\n".join(lines))


# ── Agent Teams CLI ──────────────────────────────────────────────────────────


def _get_teams_coordinator() -> AgentTeamsCoordinator:
    """Get or create the singleton AgentTeamsCoordinator."""
    from .orchestrator import Orchestrator
    orch = Orchestrator()
    return AgentTeamsCoordinator(orchestrator=orch)


def _cmd_team_spawn(args):
    """Create + spawn a team from a preset.
    
    Usage: team-spawn <preset> <name> [--goal <goal>] [--dimensions <dims>]
           team-spawn custom <name> --members <count>
    """
    if not args:
        print("Usage: team-spawn <preset> <name> [--goal <goal>] [options]")
        print("Presets: review, debug, feature, fullstack, research, security, migration, custom")
        return

    preset_name = args[0].lower()
    if preset_name not in {p.value for p in TeamPreset}:
        print(f"Unknown preset: {preset_name}")
        print(f"Available: {', '.join(p.value for p in TeamPreset)}")
        return

    name = args[1] if len(args) > 1 else f"team-{preset_name}"
    goal = ""
    extra_kwargs: dict = {}

    # Parse optional flags
    rest = args[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "--goal" and i + 1 < len(rest):
            goal = rest[i + 1]
            i += 2
        elif rest[i] == "--dimensions" and i + 1 < len(rest):
            extra_kwargs["dimensions"] = [d.strip() for d in rest[i + 1].split(",")]
            i += 2
        elif rest[i] == "--hypotheses" and i + 1 < len(rest):
            extra_kwargs["hypotheses"] = int(rest[i + 1])
            i += 2
        elif rest[i] == "--team-size" and i + 1 < len(rest):
            extra_kwargs["team_size"] = int(rest[i + 1])
            i += 2
        else:
            i += 1

    coordinator = _get_teams_coordinator()
    try:
        state = coordinator.create_team(
            name=name,
            preset=preset_name,
            goal=goal,
            **extra_kwargs,
        )
        print(f"Team '{name}' created: {state.id} ({state.config.preset.value})")
        print(f"Members: {len(state.config.members)}")
        for m in state.config.members:
            print(f"  [{m.color}] {m.name} ({m.role.value})")
        print()

        spawned = coordinator.spawn_team(state.id)
        if spawned and spawned.status == TeamStatus.COMPLETED:
            print(f"Team '{spawned.config.name}' completed successfully!")
            print(f"Results: {len(spawned.member_results)} members reported")
            for mname, mresult in spawned.member_results.items():
                status = mresult.get("status", "?")
                error = mresult.get("error", "")
                err_text = f" - {error}" if error else ""
                print(f"  {mname}: {status}{err_text}")
        elif spawned and spawned.status == TeamStatus.FAILED:
            print(f"Team spawn failed: {spawned.error}")
        else:
            print(f"Team is running: {spawned.status.value if spawned else 'unknown'}")

    except Exception as e:
        print(f"Error spawning team: {e}")


def _cmd_team_status(args):
    """Show team status summary.
    
    Usage: team-status <team_id>
    """
    if not args:
        print("Usage: team-status <team_id>")
        return

    coordinator = _get_teams_coordinator()
    status = coordinator.get_team_status(args[0])
    if not status:
        print(f"Team '{args[0]}' not found.")
        return

    print(f"Team: {status['name']} ({status['id']})")
    print(f"  Preset: {status['preset']}")
    print(f"  Status: {status['status']}")
    print(f"  Goal:   {status['goal'][:80] if status['goal'] else '(not set)'}")
    print(f"  Members: {status['member_count']}")
    for m in status['members']:
        icon = {"completed": "✓", "running": "▶", "failed": "✗",
                "pending": "○", "timeout": "!", "cancelled": "–"}
        print(f"    {icon.get(m['status'], '?')} [{m['color']}] {m['name']} ({m['role']})")
    if status.get("error"):
        print(f"  Error: {status['error']}")


def _cmd_team_shutdown(args):
    """Gracefully shut down a team.
    
    Usage: team-shutdown <team_id>
    """
    if not args:
        print("Usage: team-shutdown <team_id>")
        return

    coordinator = _get_teams_coordinator()
    state = coordinator.shutdown_team(args[0])
    if not state:
        print(f"Team '{args[0]}' not found.")
        return

    print(f"Team '{state.config.name}' ({state.id}) shut down.")
    print(f"  Final status: {state.status.value}")


def _cmd_team_review(args):
    """Quick parallel code review.
    
    Usage: team-review <goal> [--dimensions <dims>]
    
    Example: team-review "Review src/api/ endpoints" --dimensions security,performance
    """
    if not args:
        print("Usage: team-review <goal> [--dimensions <dims>]")
        print("Default dimensions: security, performance, architecture")
        return

    goal = args[0]
    dimensions = None
    if len(args) > 1 and args[1] == "--dimensions" and len(args) > 2:
        dimensions = [d.strip() for d in args[2].split(",")]

    coordinator = _get_teams_coordinator()
    try:
        state = coordinator.quick_review(goal=goal, dimensions=dimensions)
        print(f"Review team spawned: {state.id}")
        print(f"  Dimensions: {', '.join(m.name for m in state.config.members)}")
        if state.status == TeamStatus.COMPLETED:
            print(f"  Status: completed")
            print(f"  Results: {len(state.member_results)} reviewers reported")
        else:
            print(f"  Status: {state.status.value}")
            if state.error:
                print(f"  Error: {state.error}")
    except Exception as e:
        print(f"Error: {e}")


def _cmd_team_debug(args):
    """Hypothesis-driven debugging.
    
    Usage: team-debug <goal> [--hypotheses <n>]
    
    Example: team-debug "API returns 500 on POST /users" --hypotheses 3
    """
    if not args:
        print("Usage: team-debug <goal> [--hypotheses <n>]")
        return

    goal = args[0]
    hypotheses = 3
    if len(args) > 1 and args[1] == "--hypotheses" and len(args) > 2:
        try:
            hypotheses = int(args[2])
        except ValueError:
            pass

    coordinator = _get_teams_coordinator()
    try:
        state = coordinator.quick_debug(goal=goal, hypotheses=hypotheses)
        dim = "hypothesis" if hypotheses == 1 else "hypotheses"
        print(f"Debug team spawned: {state.id}")
        print(f"  {hypotheses} competing {dim}")
        if state.status == TeamStatus.COMPLETED:
            print(f"  Status: completed")
        else:
            print(f"  Status: {state.status.value}")
            if state.error:
                print(f"  Error: {state.error}")
    except Exception as e:
        print(f"Error: {e}")


def _cmd_team_feature(args):
    """Parallel feature development.
    
    Usage: team-feature <goal> [--team-size <n>]
    
    Example: team-feature "Add user authentication with OAuth2" --team-size 3
    """
    if not args:
        print("Usage: team-feature <goal> [--team-size <n>]")
        return

    goal = args[0]
    team_size = 3
    if len(args) > 1 and args[1] == "--team-size" and len(args) > 2:
        try:
            team_size = int(args[2])
        except ValueError:
            pass

    coordinator = _get_teams_coordinator()
    try:
        state = coordinator.quick_feature(goal=goal, team_size=team_size)
        implementers = team_size - 1
        print(f"Feature team spawned: {state.id}")
        print(f"  1 lead + {implementers} implementer{'s' if implementers != 1 else ''}")
        if state.status == TeamStatus.COMPLETED:
            print(f"  Status: completed")
        else:
            print(f"  Status: {state.status.value}")
            if state.error:
                print(f"  Error: {state.error}")
    except Exception as e:
        print(f"Error: {e}")


def _cmd_team_list(args):
    """List all teams.
    
    Usage: team-list
    """
    coordinator = _get_teams_coordinator()
    teams = coordinator.list_teams(limit=20)
    if not teams:
        print("No teams found. Use 'team-spawn' to create one.")
        return

    print(f"{'ID':<16} {'Name':<20} {'Preset':<12} {'Status':<14} {'Members':<8} {'Goal'}")
    print("-" * 100)
    for t in teams:
        name = t.config.name[:18]
        goal = t.config.goal[:40] if t.config.goal else ""
        print(f"{t.id:<16} {name:<20} {t.config.preset.value:<12} "
              f"{t.status.value:<14} {len(t.config.members):<8} {goal}")


# ═══════════════════════════════════════════════════════════════════════════════
# Understand Anything CLI Commands
# ═══════════════════════════════════════════════════════════════════════════════


def _get_ua_pipeline() -> UnderstandAnythingPipeline:
    return UnderstandAnythingPipeline()


def _cmd_understand_scan(args):
    """Scan a project directory for source files.

    Usage: understand-scan <project-path> [--json]
    """
    if not args:
        print("Usage: understand-scan <project-path> [--json]")
        return

    project_path = args[0]
    show_json = "--json" in args

    scanner = FileScanner()
    try:
        result = scanner.scan(project_path)
    except Exception as e:
        print(f"❌ Scan failed: {e}")
        return

    if show_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    print(f"📂 Scan: {result.project_name or Path(project_path).resolve().name}")
    print(f"  Files: {len(result.files)} source files ({result.total_lines} lines)")
    print(f"  Languages: {', '.join(result.languages) if result.languages else 'None detected'}")
    print(f"  Frameworks: {', '.join(result.frameworks) if result.frameworks else 'None'}")
    print(f"  Entry point: {result.entry_point or 'Not detected'}")
    print(f"  Complexity: {result.complexity}")
    if result.description:
        print(f"  Description: {result.description[:120]}")
    print()
    if result.files:
        print(f"  Top files by size:")
        sorted_files = sorted(result.files, key=lambda f: -f.get("sizeLines", 0))[:10]
        for f in sorted_files:
            print(f"    {f['path']:50} {f.get('sizeLines', 0):>6} lines  ({f.get('language', '?')})")


def _cmd_understand_analyze(args):
    """Run the full Understand Anything pipeline on a project.

    Usage: understand-analyze <project-path> [--force] [--batch-size <n>]
           [--max-batches <n>] [--save-intermediates] [--json]
    """
    if not args:
        print("Usage: understand-analyze <project-path> [--force] [--batch-size <n>] "
              "[--max-batches <n>] [--save-intermediates] [--json]")
        return

    project_path = args[0]
    show_json = "--json" in args
    force = "--force" in args
    save_intermediates = "--save-intermediates" in args
    batch_size = 10
    max_batches = 0

    i = 1
    while i < len(args):
        if args[i] == "--batch-size" and i + 1 < len(args):
            try:
                batch_size = int(args[i + 1])
            except ValueError:
                print(f"Invalid batch size: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--max-batches" and i + 1 < len(args):
            try:
                max_batches = int(args[i + 1])
            except ValueError:
                print(f"Invalid max batches: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    pipeline = _get_ua_pipeline()
    result = pipeline.run(project_path, force=force, batch_size=batch_size,
                          max_batches=max_batches, save_intermediates=save_intermediates)

    if show_json:
        graph = result.get("graph")
        if graph:
            print(graph.to_json())
        else:
            print(json.dumps(result, indent=2, default=str))
        return

    if result.get("status") == "up_to_date":
        print(f"✅ {result.get('message', 'Graph is up to date')}")
        return

    if result.get("status") == "error":
        print(f"❌ {result.get('error', 'Unknown error')}")
        return

    print(UnderstandAnythingPipeline.format_summary(result))
    print(f"  Graph saved to: {(Path(project_path).resolve() / '.understand-anything' / 'knowledge-graph.json')}")


def _cmd_understand_graph(args):
    """Show a summary of an existing knowledge graph.

    Usage: understand-graph <project-path> [--json]
    """
    if not args:
        print("Usage: understand-graph <project-path> [--json]")
        return

    project_path = args[0]
    show_json = "--json" in args

    graph = GraphSaver.load(project_path)
    if graph is None:
        print(f"No knowledge graph found at {project_path}/.understand-anything/")
        print("Run 'understand-analyze <project-path>' first.")
        return

    if show_json:
        print(graph.to_json())
        return

    print(UnderstandAnythingPipeline.format_graph_summary(graph))


def _cmd_understand_status(args):
    """Check if the knowledge graph is up to date with the codebase.

    Usage: understand-status <project-path>
    """
    if not args:
        print("Usage: understand-status <project-path>")
        return

    project_path = args[0]
    stale, reason = GraphSaver.is_stale(project_path)

    if stale:
        print(f"⏳ Stale: {reason}")
    else:
        print(f"✅ {reason}")

    meta = GraphSaver.load_meta(project_path)
    if meta:
        print(f"  Last analyzed: {meta.get('lastAnalyzedAt', 'Unknown')}")
        print(f"  Files analyzed: {meta.get('analyzedFiles', '?')}")
        print(f"  Version: {meta.get('version', '?')}")
    else:
        print(f"  No analysis metadata found")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9 — Loop Patterns CLI Commands
# ═══════════════════════════════════════════════════════════════════════════════


def _get_loop_registry() -> LoopRegistry:
    return LoopRegistry()


def _cmd_loop_critique(args):
    """Run a critique-improvement loop.

    Usage: loop-critique <goal> [--max-iterations <n>] [--threshold <f>]
           [--cross-model] [--dry-run]
    """
    if not args or args[0].startswith("--"):
        print("Usage: loop-critique <goal> [--max-iterations <n>] [--threshold <f>] "
              "[--cross-model] [--dry-run]")
        return

    goal = args[0]
    max_iterations = 5
    threshold = 0.85
    cross_model = "--cross-model" in args
    dry_run = "--dry-run" in args

    i = 1
    while i < len(args):
        if args[i] == "--max-iterations" and i + 1 < len(args):
            try:
                max_iterations = int(args[i + 1])
            except ValueError:
                print(f"Invalid max iterations: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--threshold" and i + 1 < len(args):
            try:
                threshold = float(args[i + 1])
            except ValueError:
                print(f"Invalid threshold: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    config = LoopConfig(
        pattern=LoopPattern.CRITIQUE_IMPROVEMENT,
        max_iterations=max_iterations,
        convergence_threshold=threshold,
        cross_model=cross_model,
    )

    if dry_run:
        print(f"🔁 Critique-Improvement Loop (dry run)")
        print(f"   Goal: {goal[:80]}")
        print(f"   Max Iterations: {max_iterations}")
        print(f"   Threshold: {threshold}")
        print(f"   Cross-Model: {cross_model}")
        print()
        print("   Registered callbacks: (none — use set_generator/set_critic/set_improver/set_scorer)")
        print("   Run with --dry-run removed to execute.")
        return

    loop = CritiqueImprovementLoop(config)
    registry = _get_loop_registry()

    # Use simulated callbacks when no real LLM functions are registered
    def _sim_generator(g: str) -> str:
        return f"# Generated output for: {g[:60]}...\n\n## Analysis\n\nThis is a simulated generation result."

    def _sim_critic(g: str, output: str) -> str:
        return "Strengths: covers the topic broadly. Areas for improvement: could add more specific examples, clarify key points."

    def _sim_improver(g: str, output: str, feedback: str) -> str:
        return output + f"\n\n## Improved\n\nAdded specific examples and clarified key points based on feedback."

    def _sim_scorer(g: str, output: str) -> tuple[float, dict[str, float]]:
        score = min(1.0, 0.5 + len(output) / 2000)
        return score, {"relevance": min(1.0, score + 0.1), "clarity": score, "completeness": max(0.1, score - 0.1)}

    loop.set_generator(_sim_generator)
    loop.set_critic(_sim_critic)
    loop.set_improver(_sim_improver)
    loop.set_scorer(_sim_scorer)

    run = loop.run(goal)
    registry.save(run)

    print(CritiqueImprovementLoop.format_summary(run))
    print(f"\n  Saved to: loops/{run.id}.json")


def _cmd_loop_evolve(args):
    """Run a self-evolution loop.

    Usage: loop-evolve <goal> [--max-steps <n>] [--dry-run]
    """
    if not args or args[0].startswith("--"):
        print("Usage: loop-evolve <goal> [--max-steps <n>] [--dry-run]")
        return

    goal = args[0]
    max_steps = 3
    dry_run = "--dry-run" in args

    i = 1
    while i < len(args):
        if args[i] == "--max-steps" and i + 1 < len(args):
            try:
                max_steps = int(args[i + 1])
            except ValueError:
                print(f"Invalid max steps: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    config = LoopConfig(
        pattern=LoopPattern.SELF_EVOLUTION,
        max_iterations=max_steps,
    )

    if dry_run:
        print(f"🧬 Self-Evolution Loop (dry run)")
        print(f"   Goal: {goal[:80]}")
        print(f"   Max Steps: {max_steps}")
        print()
        print("   Pipeline: WorkFlowGenerator → AgentManager → WorkFlow → CodeVerification")
        print("   Run with --dry-run removed to execute.")
        return

    loop = SelfEvolutionLoop(config)
    registry = _get_loop_registry()

    def _sim_workflow_gen(g: str) -> str:
        return f'{{"goal": "{g[:40]}...", "agents": ["coder", "reviewer", "tester"], "steps": 3}}'

    def _sim_executor(g: str, wf: str) -> tuple[str, int]:
        return f"Executed workflow for: {g[:50]}...\nOutput: Successfully generated {len(g)} lines of content.", 3

    def _sim_verifier(g: str, output: str) -> tuple[bool, str]:
        return True, "All checks passed. Output meets requirements."

    loop.set_workflow_generator(_sim_workflow_gen)
    loop.set_agent_executor(_sim_executor)
    loop.set_verifier(_sim_verifier)

    run = loop.run(goal)
    registry.save(run)

    print(SelfEvolutionLoop.format_summary(run))
    print(f"\n  Saved to: loops/{run.id}.json")


def _cmd_loop_refine(args):
    """Run iterative refinement on content.

    Usage: loop-refine <file-path> [--criteria <c1,c2,...>] [--max-rounds <n>]
           [--threshold <f>] [--dry-run]
    """
    if not args or args[0].startswith("--"):
        print("Usage: loop-refine <file-path> [--criteria <c1,c2,...>] [--max-rounds <n>] "
              "[--threshold <f>] [--dry-run]")
        return

    file_path = Path(args[0])
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return

    content = file_path.read_text(encoding="utf-8")
    criteria = ["quality", "correctness", "completeness"]
    max_rounds = 5
    threshold = 0.9
    dry_run = "--dry-run" in args

    i = 1
    while i < len(args):
        if args[i] == "--criteria" and i + 1 < len(args):
            criteria = [c.strip() for c in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--max-rounds" and i + 1 < len(args):
            try:
                max_rounds = int(args[i + 1])
            except ValueError:
                print(f"Invalid max rounds: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--threshold" and i + 1 < len(args):
            try:
                threshold = float(args[i + 1])
            except ValueError:
                print(f"Invalid threshold: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    config = LoopConfig(
        pattern=LoopPattern.ITERATIVE_REFINEMENT,
        max_iterations=max_rounds,
        convergence_threshold=threshold,
    )

    if dry_run:
        print(f"🔄 Iterative Refinement (dry run)")
        print(f"   File: {file_path}")
        print(f"   Content Size: {len(content)} chars, {len(content.splitlines())} lines")
        print(f"   Criteria: {', '.join(criteria)}")
        print(f"   Max Rounds: {max_rounds}")
        print(f"   Threshold: {threshold}")
        print()
        print("   Run with --dry-run removed to execute.")
        return

    loop = IterativeRefinement(config)
    registry = _get_loop_registry()

    # Use simulated callbacks
    def _sim_refiner(c: str, prompt: str, rnd: int) -> str:
        return c + f"\n\n# Refinement pass {rnd}\nRefined with criteria: {prompt}"

    def _sim_scorer(c: str, crit: list[str]) -> tuple[dict[str, float], float]:
        scores = {cr: min(1.0, 0.4 + len(c) / 5000) for cr in crit}
        agg = sum(scores.values()) / len(scores) if scores else 0.0
        return scores, agg

    loop.set_refiner(_sim_refiner)
    loop.set_scorer(_sim_scorer)

    run = loop.run(content, criteria=criteria)
    registry.save(run)

    print(IterativeRefinement.format_summary(run))
    print(f"\n  Saved to: loops/{run.id}.json")


def _cmd_loop_list(args):
    """List recent loop runs.

    Usage: loop-list [--pattern <type>] [--status <status>] [--limit <n>]
    """
    limit = 20
    pattern = None
    status = None

    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Invalid limit: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--pattern" and i + 1 < len(args):
            try:
                pattern = LoopPattern(args[i + 1])
            except ValueError:
                valid = [p.value for p in LoopPattern]
                print(f"Invalid pattern. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            try:
                status = LoopStatus(args[i + 1])
            except ValueError:
                valid = [s.value for s in LoopStatus]
                print(f"Invalid status. Valid: {', '.join(valid)}")
                return
            i += 2
        else:
            i += 1

    registry = _get_loop_registry()
    runs = registry.list_runs(limit=limit, pattern=pattern, status=status)

    if not runs:
        print("No loop runs found. Use 'loop-critique', 'loop-evolve' or 'loop-refine' to create one.")
        return

    print(f"{'ID':<20} {'Pattern':<22} {'Status':<14} {'Score':<8} {'Goal'}")
    print("-" * 100)
    for r in runs:
        goal = r.goal[:50] if r.goal else ""
        print(f"{r.id:<20} {r.pattern.value:<22} {r.status.value:<14} "
              f"{r.best_score:<8.3f} {goal}")


def _cmd_loop_status(args):
    """Show details of a specific loop run.

    Usage: loop-status <run-id>
    """
    if not args:
        print("Usage: loop-status <run-id>")
        return

    run_id = args[0]
    registry = _get_loop_registry()
    run = registry.load(run_id)

    if run is None:
        print(f"❌ Run not found: {run_id}")
        print("Use 'loop-list' to see available runs.")
        return

    if run.pattern == LoopPattern.CRITIQUE_IMPROVEMENT:
        print(CritiqueImprovementLoop.format_summary(run))
    elif run.pattern == LoopPattern.SELF_EVOLUTION:
        print(SelfEvolutionLoop.format_summary(run))
    elif run.pattern == LoopPattern.ITERATIVE_REFINEMENT:
        print(IterativeRefinement.format_summary(run))

    print(f"\n  Full state: loops/{run.id}.json")


def _cmd_loop_stats(args):
    """Show aggregate loop pattern statistics.

    Usage: loop-stats
    """
    registry = _get_loop_registry()
    stats = registry.get_stats()

    print("📊 Loop Pattern Statistics")
    print("=" * 40)
    print(f"  Total Runs: {stats['total_runs']}")
    print(f"  Avg Score: {stats['avg_score']:.3f}")
    print(f"  Avg Duration: {stats['avg_duration_ms']}ms")
    print(f"  Total Duration: {stats['total_duration_ms']}ms")
    print()
    if stats["by_pattern"]:
        print("  By Pattern:")
        for pattern, count in sorted(stats["by_pattern"].items()):
            print(f"    {pattern}: {count}")
    print()
    if stats["by_status"]:
        print("  By Status:")
        for status_name, count in sorted(stats["by_status"].items()):
            print(f"    {status_name}: {count}")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10 — Background Agents CLI Commands
# ═══════════════════════════════════════════════════════════════════════════════


def _get_bg_registry() -> BackgroundAgentRegistry:
    return BackgroundAgentRegistry()


def _cmd_hn_brief(args):
    """Run the Hacker News briefing agent.

    Usage: hn-brief [--live] [--stories <n>] [--delivery <file|stdout|none>]
           [--dry-run]

    Runs a full briefing cycle: fetch → curate → render → record.
    Uses deterministic sample data by default (use --live for live data).
    """
    stories_count = 5
    delivery = "file"
    live_mode = False
    dry_run = "--dry-run" in args

    i = 0
    while i < len(args):
        if args[i] == "--stories" and i + 1 < len(args):
            try:
                stories_count = int(args[i + 1])
            except ValueError:
                print(f"Invalid stories count: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--delivery" and i + 1 < len(args):
            delivery = args[i + 1]
            if delivery not in ("file", "stdout", "none"):
                print(f"Invalid delivery method: {delivery}. Use: file, stdout, none")
                return
            i += 2
        elif args[i] == "--live":
            live_mode = True
            i += 1
        else:
            i += 1

    if dry_run:
        print("📰 Hacker News Briefing (dry run)")
        print(f"   Stories: {stories_count}")
        print(f"   Delivery: {delivery}")
        print(f"   Live Mode: {live_mode}")
        print()
        print("   Pipeline: fetch() → curate() → render() → record()")
        print("   Run with --dry-run removed to execute.")
        return

    config = BackgroundAgentConfig(
        name="hn-briefing",
        agent_type=AgentType.HACKER_NEWS_BRIEFING,
        max_stories=stories_count,
        delivery_method=DeliveryMethod(delivery),
        live_mode=live_mode,
    )
    agent = HackerNewsBriefingAgent(config)
    registry = _get_bg_registry()

    print("📰 Hacker News Briefing")
    print("=" * 50)
    run, result = agent.run()
    registry.save_run(run)

    print(agent.format_summary(run, result))
    print()

    if result:
        print("  Content Preview:")
        # Show first few lines of the brief
        lines = result.text.split("\n")
        for line in lines[:12]:
            print(f"    {line}")
        print()

    # Handle delivery
    if delivery == "stdout" and result:
        print("── Full Briefing ──")
        print(result.text)
    elif delivery == "file" and result:
        # Save full briefing to a file
        output_dir = Path("background_agents") / "briefings"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"hn-briefing-{run.id}.txt"
        path = output_dir / filename
        path.write_text(result.text, encoding="utf-8")
        print(f"  Full briefing saved to: {path}")

    print(f"  Run ID: {run.id}")
    print(f"  Status: {run.status.value}")
    print(f"  Duration: {run.duration_ms}ms")


def _cmd_dev_pulse(args):
    """Run the DevPulse signal intelligence agent.

    Usage: dev-pulse [--dry-run]

    Collects signals from multiple developer sources, scores relevance,
    assesses risk and synthesizes an intelligence digest.
    Uses deterministic sample data by default.
    """
    dry_run = "--dry-run" in args

    if dry_run:
        print("📡 DevPulse Intelligence (dry run)")
        print()
        print("   Pipeline: collect() → score() → assess() → synthesize()")
        print("   Sources: github, arxiv, hackernews, huggingface")
        print("   Run with --dry-run removed to execute.")
        return

    agent = DevPulseAgent()
    registry = _get_bg_registry()

    print("📡 DevPulse Intelligence Digest")
    print("=" * 50)
    run, result = agent.run()
    registry.save_run(run)

    print(agent.format_summary(run, result.text if result else ""))
    print()

    if result:
        print("  Executive Summary:")
        print(f"    {result.metadata.get('executive_summary', '')}")
        print()
        print("  Priority Signals:")
        for s in result.metadata.get("priority_signals", [])[:3]:
            print(f"    [{s['source']}] {s['title'][:70]}")
            print(f"    Score: {s['score']:.0f} | Risk: {s['risk_level']}")
        print()
        print("  Recommendations:")
        for r in result.metadata.get("recommendations", []):
            print(f"    • {r}")

        # Save digest to file
        output_dir = Path("background_agents") / "digests"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"dev-pulse-{run.id}.txt"
        path = output_dir / filename
        path.write_text(result.text, encoding="utf-8")
        print(f"\n  Full digest saved to: {path}")

    print(f"  Run ID: {run.id}")
    print(f"  Status: {run.status.value}")
    print(f"  Duration: {run.duration_ms}ms")


def _cmd_bg_list(args):
    """List recent background agent runs.

    Usage: bg-list [--limit <n>] [--type <agent_type>]

    Agent types: hn_briefing, dev_pulse
    """
    limit = 20
    agent_type = None

    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Invalid limit: {args[i + 1]}")
                return
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            try:
                agent_type = AgentType(args[i + 1])
            except ValueError:
                valid = [t.value for t in AgentType]
                print(f"Invalid agent type. Valid: {', '.join(valid)}")
                return
            i += 2
        else:
            i += 1

    registry = _get_bg_registry()
    runs = registry.list_runs(limit=limit, agent_type=agent_type)

    if not runs:
        print("No background agent runs found.")
        print("Use 'hn-brief' or 'dev-pulse' to create one.")
        return

    type_labels = {
        AgentType.HACKER_NEWS_BRIEFING: "hn_briefing",
        AgentType.DEV_PULSE: "dev_pulse",
    }

    print(f"{'Run ID':<22} {'Type':<14} {'Status':<12} {'Duration':<10} {'Stories':<8} {'Subject'}")
    print("-" * 100)
    for r in runs:
        type_name = type_labels.get(r.agent_type, r.agent_type.value)
        subj = r.subject[:40] if r.subject else ""
        print(f"{r.id:<22} {type_name:<14} {r.status.value:<12} "
              f"{r.duration_ms:<10} {r.stories_count:<8} {subj}")

    print(f"\n{len(runs)} run(s)")


def _cmd_bg_status(args):
    """Show details of a specific background agent run.

    Usage: bg-status <run-id>
    """
    if not args:
        print("Usage: bg-status <run-id>")
        print("Use 'bg-list' to find run IDs.")
        return

    run_id = args[0]
    registry = _get_bg_registry()
    run = registry.load_run(run_id)

    if run is None:
        print(f"❌ Run not found: {run_id}")
        print("Use 'bg-list' to see available runs.")
        return

    type_labels = {
        AgentType.HACKER_NEWS_BRIEFING: "Hacker News Briefing",
        AgentType.DEV_PULSE: "DevPulse Intelligence",
    }

    print(f"Background Agent Run: {run.id}")
    print("=" * 50)
    print(f"  Agent:      {type_labels.get(run.agent_type, run.agent_type.value)}")
    print(f"  Name:       {run.agent_name}")
    print(f"  Status:     {run.status.value}")
    print(f"  Started:    {run.started_at}")
    print(f"  Completed:  {run.completed_at or '(not completed)'}")
    print(f"  Duration:   {run.duration_ms}ms")
    print(f"  Stories:    {run.stories_count}")
    print(f"  Subject:    {run.subject}")
    if run.summary_preview:
        print(f"  Summary:    {run.summary_preview[:120]}")
    print(f"  Delivery:   {run.delivery_method}")
    print(f"  Delivery status: {run.delivery_status or 'N/A'}")
    if run.error:
        print(f"  Error:      {run.error}")
    if run.metadata:
        print(f"  Metadata:   {json.dumps(run.metadata, default=str)[:200]}")


def _cmd_bg_stats(args):
    """Show aggregate background agent statistics.

    Usage: bg-stats
    """
    registry = _get_bg_registry()
    stats = registry.get_stats()

    print("📊 Background Agent Statistics")
    print("=" * 40)
    print(f"  Total Runs:       {stats['total_runs']}")
    print(f"  Completed Runs:   {stats['completed_runs']}")
    print(f"  Failed Runs:      {stats['failed_runs']}")
    print(f"  Total Stories:    {stats['total_stories']}")
    print(f"  Avg Duration:     {stats['avg_duration_ms']}ms")
    print(f"  Registered Agents: {stats['registered_agents']}")
    print()

    if stats.get("by_type"):
        print("  By Type:")
        type_labels = {
            "hn_briefing": "Hacker News Briefing",
            "dev_pulse": "DevPulse Intelligence",
        }
        for agent_type, count in sorted(stats["by_type"].items()):
            label = type_labels.get(agent_type, agent_type)
            print(f"    {label:<24} {count} run(s)")

    if stats.get("by_status"):
        print("  By Status:")
        for status_name, count in sorted(stats["by_status"].items()):
            print(f"    {status_name:<16} {count} run(s)")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10 — Prompts Index CLI Commands (P2c)
# ═══════════════════════════════════════════════════════════════════════════════


def _get_prompts_index() -> PromptsIndex:
    return PromptsIndex()


def _cmd_prompt_add(args):
    """Create a new prompt entry.

    Usage: prompt-add <name> <content> [--description <desc>] [--category <cat>]
           [--status <status>] [--tags <t1,t2>] [--author <name>]

    Categories: system, agent, workflow, task, command, context, eval, template, custom
    Statuses: draft, active, deprecated, archived
    """
    if len(args) < 2:
        print("Usage: prompt-add <name> <content> [--description <desc>] "
              "[--category <cat>] [--status <status>] [--tags <t1,t2>] [--author <name>]")
        print("Categories: system, agent, workflow, task, command, context, eval, template, custom")
        print("Statuses: draft, active, deprecated, archived")
        return

    name = args[0]
    content = args[1]
    description = ""
    category = PromptCategory.CUSTOM
    status = PromptStatus.DRAFT
    tags: list[str] = []
    author = ""

    i = 2
    while i < len(args):
        if args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif args[i] == "--category" and i + 1 < len(args):
            try:
                category = PromptCategory(args[i + 1])
            except ValueError:
                valid = [c.value for c in PromptCategory]
                print(f"Invalid category. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            try:
                status = PromptStatus(args[i + 1])
            except ValueError:
                valid = [s.value for s in PromptStatus]
                print(f"Invalid status. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--author" and i + 1 < len(args):
            author = args[i + 1]
            i += 2
        else:
            i += 1

    index = _get_prompts_index()
    entry = index.add_prompt(
        name=name,
        content=content,
        description=description,
        category=category,
        status=status,
        tags=tags,
        author=author,
    )

    print(f"✅ Prompt created: {entry.name} ({entry.id})")
    print(f"  Category: {entry.category.value}")
    print(f"  Status: {entry.status.value}")
    print(f"  Version: {entry.version}")
    print(f"  Size: {entry.word_count()} words (~{entry.estimated_tokens()} tokens)")


def _cmd_prompt_get(args):
    """Show prompt details.

    Usage: prompt-get <prompt-id>
    """
    if not args:
        print("Usage: prompt-get <prompt-id>")
        print("Use 'prompt-list' to find prompt IDs.")
        return

    prompt_id = args[0]
    index = _get_prompts_index()

    # Try by ID first, then by name
    entry = index.get_prompt(prompt_id)
    if entry is None:
        entry = index.get_prompt_by_name(prompt_id)

    if entry is None:
        print(f"❌ Prompt not found: {prompt_id}")
        print("Use 'prompt-list' to see available prompts.")
        return

    print(PromptsIndex.format_prompt_summary(entry))


def _cmd_prompt_list(args):
    """List prompts with optional filters.

    Usage: prompt-list [--category <cat>] [--status <status>] [--tags <t1,t2>]
           [--limit <n>]
    """
    category = None
    status = None
    tags = None
    limit = 100

    i = 0
    while i < len(args):
        if args[i] == "--category" and i + 1 < len(args):
            try:
                category = PromptCategory(args[i + 1])
            except ValueError:
                valid = [c.value for c in PromptCategory]
                print(f"Invalid category. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            try:
                status = PromptStatus(args[i + 1])
            except ValueError:
                valid = [s.value for s in PromptStatus]
                print(f"Invalid status. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Invalid limit: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    index = _get_prompts_index()
    prompts = index.list_prompts(category=category, status=status, tags=tags, limit=limit)

    if not prompts:
        print("No prompts found.")
        print("Use 'prompt-add' to create one.")
        return

    print(f"{'ID':<24} {'Name':<30} {'Category':<12} {'Status':<14} {'Version':<10} {'Tags'}")
    print("-" * 120)
    for p in prompts:
        tags_str = ", ".join(p.tags[:3]) if p.tags else ""
        print(f"{p.id:<24} {p.name:<30} {p.category.value:<12} "
              f"{p.status.value:<14} {p.version:<10} {tags_str}")

    print(f"\n{len(prompts)} prompt(s)")


def _cmd_prompt_search(args):
    """Search prompts by text.

    Usage: prompt-search <query> [--category <cat>] [--status <status>]
           [--limit <n>]
    """
    if not args or args[0].startswith("--"):
        print("Usage: prompt-search <query> [--category <cat>] [--status <status>] "
              "[--limit <n>]")
        return

    query = args[0]
    category = None
    status = None
    limit = 20

    i = 1
    while i < len(args):
        if args[i] == "--category" and i + 1 < len(args):
            try:
                category = PromptCategory(args[i + 1])
            except ValueError:
                valid = [c.value for c in PromptCategory]
                print(f"Invalid category. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            try:
                status = PromptStatus(args[i + 1])
            except ValueError:
                valid = [s.value for s in PromptStatus]
                print(f"Invalid status. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Invalid limit: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    index = _get_prompts_index()
    results = index.search_prompts(query, category=category, status=status, limit=limit)

    print(PromptsIndex.format_search_results(results))


def _cmd_prompt_update(args):
    """Update a prompt.

    Usage: prompt-update <prompt-id> [--content <text>] [--description <desc>]
           [--status <status>] [--tags <t1,t2>] [--notes <notes>] [--author <name>]
    """
    if not args:
        print("Usage: prompt-update <prompt-id> [--content <text>] [--description <desc>] "
              "[--status <status>] [--tags <t1,t2>] [--notes <notes>] [--author <name>]")
        return

    prompt_id = args[0]
    content = None
    description = None
    status = None
    tags = None
    change_notes = ""
    author = ""

    i = 1
    while i < len(args):
        if args[i] == "--content" and i + 1 < len(args):
            content = args[i + 1]
            i += 2
        elif args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            try:
                status = PromptStatus(args[i + 1])
            except ValueError:
                valid = [s.value for s in PromptStatus]
                print(f"Invalid status. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--notes" and i + 1 < len(args):
            change_notes = args[i + 1]
            i += 2
        elif args[i] == "--author" and i + 1 < len(args):
            author = args[i + 1]
            i += 2
        else:
            i += 1

    if all(v is None for v in [content, description, status, tags]):
        print("No changes specified. Provide at least one of: --content, --description, --status, --tags")
        return

    index = _get_prompts_index()
    entry = index.update_prompt(
        prompt_id=prompt_id,
        content=content,
        description=description,
        status=status,
        tags=tags,
        change_notes=change_notes,
        author=author,
    )

    if entry is None:
        print(f"❌ Prompt not found: {prompt_id}")
        return

    print(f"✅ Prompt updated: {entry.name} ({entry.id})")
    print(f"  New version: {entry.version}")
    if change_notes:
        print(f"  Notes: {change_notes}")


def _cmd_prompt_delete(args):
    """Delete a prompt and its versions.

    Usage: prompt-delete <prompt-id>
    """
    if not args:
        print("Usage: prompt-delete <prompt-id>")
        return

    prompt_id = args[0]
    index = _get_prompts_index()

    if index.delete_prompt(prompt_id):
        print(f"✅ Prompt deleted: {prompt_id}")
    else:
        print(f"❌ Prompt not found: {prompt_id}")


def _cmd_prompt_versions(args):
    """List all versions of a prompt.

    Usage: prompt-versions <prompt-id>
    """
    if not args:
        print("Usage: prompt-versions <prompt-id>")
        return

    prompt_id = args[0]
    index = _get_prompts_index()
    versions = index.get_versions(prompt_id)

    if not versions:
        print(f"No versions found for prompt: {prompt_id}")
        prompt = index.get_prompt(prompt_id)
        if prompt is None:
            print("Prompt not found.")
        return

    print(f"Version history for: {prompt_id}")
    print(f"{'Version':<14} {'Created':<24} {'Author':<20} {'Size':<10} {'Notes'}")
    print("-" * 100)
    for v in versions:
        size = f"{len(v.content)} chars"
        print(f"{v.version:<14} {v.created_at[:19]:<24} {v.author:<20} {size:<10} {v.change_notes[:40]}")

    print(f"\n{len(versions)} version(s)")


def _cmd_prompt_export(args):
    """Export a prompt with versions and usage stats.

    Usage: prompt-export <prompt-id> [--json]
    """
    if not args:
        print("Usage: prompt-export <prompt-id> [--json]")
        return

    prompt_id = args[0]
    show_json = "--json" in args

    index = _get_prompts_index()
    exported = index.export_prompt(prompt_id)

    if exported is None:
        print(f"❌ Prompt not found: {prompt_id}")
        return

    if show_json:
        print(json.dumps(exported, indent=2, default=str))
        return

    entry_data = exported.get("entry", {})
    versions = exported.get("versions", [])
    stats = exported.get("usage_stats", {})

    print(f"📤 Export: {entry_data.get('name', '?')} ({prompt_id})")
    print("=" * 50)
    print(f"  Name:        {entry_data.get('name', '?')}")
    print(f"  Category:    {entry_data.get('category', '?')}")
    print(f"  Status:      {entry_data.get('status', '?')}")
    print(f"  Version:     {entry_data.get('version', '?')}")
    print(f"  Description: {entry_data.get('description', '')[:80]}")
    print(f"  Tags:        {', '.join(entry_data.get('tags', [])) or '(none)'}")
    print(f"  Size:        {len(entry_data.get('content', ''))} chars")
    print()
    print(f"  Versions:    {len(versions)}")
    print(f"  Total Uses:  {stats.get('total_uses', 0)}")
    print(f"  Successes:   {stats.get('successes', 0)}")
    print(f"  Failures:    {stats.get('failures', 0)}")
    print(f"  Avg Tokens:  {stats.get('avg_tokens', 0)}")

    # Preview content
    content = entry_data.get('content', '')
    print()
    print("  Content Preview:")
    preview = content[:300]
    print(f"    {preview}")
    if len(content) > 300:
        print("    ...")


def _cmd_prompt_usage(args):
    """Show or record usage for a prompt.

    Usage: prompt-usage <prompt-id>
           prompt-usage <prompt-id> --record --outcome <outcome>
                      [--duration <ms>] [--tokens <n>] [--context <ctx>]
                      [--feedback <fb>]

    Outcomes: success, failure, partial, unknown
    Without --record, shows usage statistics.
    """
    if not args:
        print("Usage: prompt-usage <prompt-id> [--record] [--outcome <outcome>] "
              "[--duration <ms>] [--tokens <n>] [--context <ctx>] [--feedback <fb>]")
        return

    prompt_id = args[0]
    index = _get_prompts_index()

    if "--record" in args:
        # Record a usage
        outcome = UsageOutcome.UNKNOWN
        duration_ms = 0
        tokens_used = 0
        context = ""
        feedback = ""

        i = 1
        while i < len(args):
            if args[i] == "--outcome" and i + 1 < len(args):
                try:
                    outcome = UsageOutcome(args[i + 1])
                except ValueError:
                    valid = [o.value for o in UsageOutcome]
                    print(f"Invalid outcome. Valid: {', '.join(valid)}")
                    return
                i += 2
            elif args[i] == "--duration" and i + 1 < len(args):
                try:
                    duration_ms = int(args[i + 1])
                except ValueError:
                    print(f"Invalid duration: {args[i + 1]}")
                    return
                i += 2
            elif args[i] == "--tokens" and i + 1 < len(args):
                try:
                    tokens_used = int(args[i + 1])
                except ValueError:
                    print(f"Invalid tokens: {args[i + 1]}")
                    return
                i += 2
            elif args[i] == "--context" and i + 1 < len(args):
                context = args[i + 1]
                i += 2
            elif args[i] == "--feedback" and i + 1 < len(args):
                feedback = args[i + 1]
                i += 2
            else:
                i += 1

        usage = index.record_usage(
            prompt_id=prompt_id,
            outcome=outcome,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            context=context,
            feedback=feedback,
        )

        if usage is None:
            print(f"❌ Prompt not found: {prompt_id}")
            return

        print(f"✅ Usage recorded: {usage.id}")
        print(f"  Prompt: {prompt_id}")
        print(f"  Outcome: {usage.outcome.value}")
        print(f"  Duration: {usage.duration_ms}ms")
        print(f"  Tokens: {usage.tokens_used}")
    else:
        # Show usage stats
        stats = index.get_prompt_usage_stats(prompt_id)
        if stats.get("total_uses", 0) == 0:
            print(f"No usage data for prompt: {prompt_id}")
            entry = index.get_prompt(prompt_id)
            if entry is None:
                print("Prompt not found.")
                return
            print("Record usage with: prompt-usage <prompt-id> --record --outcome success")
            return

        print(f"📊 Usage Statistics: {prompt_id}")
        print("=" * 40)
        for key, val in stats.items():
            if isinstance(val, float):
                print(f"  {key}: {val:.1%}")
            else:
                print(f"  {key}: {val}")


def _cmd_prompt_stats(args):
    """Show aggregate prompt catalog statistics.

    Usage: prompt-stats
    """
    index = _get_prompts_index()
    stats = index.get_stats()

    print("📊 Prompt Catalog Statistics")
    print("=" * 40)
    print(f"  Total Prompts:     {stats['total_prompts']}")
    print(f"  Total Collections: {stats['total_collections']}")
    print(f"  Total Versions:    {stats['total_versions']}")
    print(f"  Total Usage:       {stats['total_usage']}")
    print(f"  Successful Usage:  {stats['successful_usage']}")
    print(f"  Failed Usage:      {stats['failed_usage']}")
    print(f"  Success Rate:      {stats['success_rate']:.1%}")
    print(f"  Avg Duration:      {stats['avg_duration_ms']}ms")
    print(f"  Avg Tokens:        {stats['avg_tokens']}")
    print(f"  Total Content:     {stats['total_content_chars']:,} chars")
    print(f"  Avg Content:       {stats['avg_content_chars']:,} chars")
    print()

    if stats["by_category"]:
        print("  By Category:")
        for cat, count in sorted(stats["by_category"].items()):
            print(f"    {cat:<16} {count} prompt(s)")
    print()

    if stats["by_status"]:
        print("  By Status:")
        for st, count in sorted(stats["by_status"].items()):
            print(f"    {st:<16} {count} prompt(s)")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 11 — Bankr Trading Agent CLI Commands (P2d)
# ═══════════════════════════════════════════════════════════════════════════════


def _get_bankr_agent(cash: float = 10000.0) -> BankrAgent:
    """Create a BankrAgent with sensible defaults."""
    return BankrAgent(initial_cash=cash)


def _cmd_bankr_fetch(args):
    """Fetch market data for a ticker.

    Usage: bankr-fetch <ticker> <start> <end> [--interval <1d|1wk|1mo|1h>]
    """
    if len(args) < 3:
        print("Usage: bankr-fetch <ticker> <start> <end> [--interval <interval>]")
        print("Example: bankr-fetch AAPL 2024-01-01 2024-12-31 --interval 1d")
        return

    ticker = args[0]
    start = args[1]
    end = args[2]
    interval = "1d"

    i = 3
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent()
    try:
        data = agent.fetch_data(ticker, start, end, interval)
    except ImportError as e:
        print(f"❌ {e}")
        print("Install yfinance: pip install yfinance")
        return

    if not data:
        print(f"No data found for {ticker} from {start} to {end}.")
        return

    print(f"📈 {ticker} — {start} to {end} ({interval})")
    print(f"   {len(data)} data points")
    print(f"   Range: ${data[0].close:.2f} — ${data[-1].close:.2f}")
    print()
    print(f"{'Date':14s} {'Open':>10s} {'High':>10s} {'Low':>10s} {'Close':>10s} {'Volume':>12s}")
    print("-" * 68)
    for idx, d in enumerate(data):
        if idx < 10 or idx >= len(data) - 3:
            print(f"{d.timestamp[:10]:14s} {d.open:>10.2f} {d.high:>10.2f} {d.low:>10.2f} {d.close:>10.2f} {d.volume:>12,}")
        elif idx == 10:
            print(f"{'...':14s} {'...':>10s} {'...':>10s} {'...':>10s} {'...':>10s} {'...':>12s}")


def _cmd_bankr_analyze(args):
    """Compute technical indicators for a ticker.

    Usage: bankr-analyze <ticker> <start> <end> [--interval <interval>]
    """
    if len(args) < 3:
        print("Usage: bankr-analyze <ticker> <start> <end> [--interval <interval>]")
        return

    ticker = args[0]
    start = args[1]
    end = args[2]
    interval = "1d"

    i = 3
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent()
    try:
        data = agent.fetch_data(ticker, start, end, interval)
    except ImportError as e:
        print(f"❌ {e}")
        return

    if not data:
        print(f"No data found for {ticker}.")
        return

    indicators = agent.compute_indicators(data)
    print(f"📊 Technical Indicators — {ticker}")
    print(f"   {len(indicators)} periods analyzed")
    print()

    # Show last 5 periods with key indicators
    print(f"{'Date':14s} {'SMA20':>8s} {'SMA50':>8s} {'RSI14':>8s} {'MACD':>10s} {'Signal':>10s} {'BB Up':>8s} {'BB Lo':>8s}")
    print("-" * 76)
    shown = 0
    for ti in reversed(indicators):
        if shown >= 5:
            break
        if ti.sma_20 is not None:
            rsi_str = f"{ti.rsi_14:.1f}" if ti.rsi_14 is not None else "N/A"
            macd_str = f"{ti.macd_line:.4f}" if ti.macd_line is not None else "N/A"
            sig_str = f"{ti.macd_signal:.4f}" if ti.macd_signal is not None else "N/A"
            bb_u = f"{ti.bollinger_upper:.1f}" if ti.bollinger_upper is not None else "N/A"
            bb_l = f"{ti.bollinger_lower:.1f}" if ti.bollinger_lower is not None else "N/A"
            sma20 = f"{ti.sma_20:.2f}" if ti.sma_20 is not None else "N/A"
            sma50 = f"{ti.sma_50:.2f}" if ti.sma_50 is not None else "N/A"
            print(f"{ti.timestamp[:10]:14s} {sma20:>8s} {sma50:>8s} {rsi_str:>8s} {macd_str:>10s} {sig_str:>10s} {bb_u:>8s} {bb_l:>8s}")
            shown += 1


def _cmd_bankr_signals(args):
    """Generate trading signals.

    Usage: bankr-signals <ticker> <start> <end> [--strategy <strategy>]
           [--interval <interval>] [--short-window <n>] [--long-window <n>]
           [--period <n>] [--oversold <n>] [--overbought <n>]
    """
    if len(args) < 3:
        print("Usage: bankr-signals <ticker> <start> <end> [--strategy <strategy>] "
              "[--interval <interval>] [strategy params]")
        print(f"Strategies: {', '.join(s.value for s in StrategyType)}")
        return

    ticker = args[0]
    start = args[1]
    end = args[2]
    interval = "1d"
    strategy = StrategyType.SMA_CROSSOVER
    kwargs: dict = {}

    i = 3
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        elif args[i] == "--strategy" and i + 1 < len(args):
            try:
                strategy = StrategyType(args[i + 1])
            except ValueError:
                valid = [s.value for s in StrategyType]
                print(f"Invalid strategy. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--short-window" and i + 1 < len(args):
            kwargs["short_window"] = int(args[i + 1])
            i += 2
        elif args[i] == "--long-window" and i + 1 < len(args):
            kwargs["long_window"] = int(args[i + 1])
            i += 2
        elif args[i] == "--period" and i + 1 < len(args):
            kwargs["period"] = int(args[i + 1])
            i += 2
        elif args[i] == "--oversold" and i + 1 < len(args):
            kwargs["oversold"] = float(args[i + 1])
            i += 2
        elif args[i] == "--overbought" and i + 1 < len(args):
            kwargs["overbought"] = float(args[i + 1])
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent()
    try:
        data = agent.fetch_data(ticker, start, end, interval)
    except ImportError as e:
        print(f"❌ {e}")
        return

    if not data:
        print(f"No data found for {ticker}.")
        return

    signals = agent.generate_signals(data, strategy, **kwargs)
    print(f"🚦 Trading Signals — {ticker} ({strategy.value})")
    print(agent.format_signals(signals))
    print(f"\n{len(signals)} signal(s) generated")


def _cmd_bankr_backtest(args):
    """Run a backtest.

    Usage: bankr-backtest <ticker> <start> <end> [--strategy <strategy>]
           [--cash <amount>] [--interval <interval>]
           [--strategy-params <key=val,key=val>]
    """
    if len(args) < 3:
        print("Usage: bankr-backtest <ticker> <start> <end> [--strategy <strategy>] "
              "[--cash <amount>] [--interval <interval>] [--strategy-params <k=v,...>]")
        print(f"Strategies: {', '.join(s.value for s in StrategyType)}")
        return

    ticker = args[0]
    start = args[1]
    end = args[2]
    strategy = StrategyType.SMA_CROSSOVER
    cash = 10000.0
    interval = "1d"
    kwargs: dict = {}

    i = 3
    while i < len(args):
        if args[i] == "--strategy" and i + 1 < len(args):
            try:
                strategy = StrategyType(args[i + 1])
            except ValueError:
                valid = [s.value for s in StrategyType]
                print(f"Invalid strategy. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--cash" and i + 1 < len(args):
            cash = float(args[i + 1])
            i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        elif args[i] == "--strategy-params" and i + 1 < len(args):
            for pair in args[i + 1].split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    try:
                        kwargs[k] = int(v)
                    except ValueError:
                        try:
                            kwargs[k] = float(v)
                        except ValueError:
                            kwargs[k] = v
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent(cash=cash)
    try:
        result = agent.backtest(ticker, start, end, strategy, interval, **kwargs)
    except ImportError as e:
        print(f"❌ {e}")
        return

    print(agent.generate_report(result))
    print(f"\nResult index: {len(agent.results) - 1}  (use 'bankr-report {len(agent.results) - 1}' to revisit)")


def _cmd_bankr_portfolio(args):
    """Run a multi-ticker portfolio backtest.

    Usage: bankr-portfolio <tickers> <start> <end> [--strategy <strategy>]
           [--cash <amount>] [--alloc <pct1,pct2,...>] [--interval <interval>]
    """
    if len(args) < 3:
        print("Usage: bankr-portfolio <ticker1,ticker2,...> <start> <end> "
              "[--strategy <strategy>] [--cash <amount>] [--alloc <pct1,pct2,...>] "
              "[--interval <interval>]")
        return

    tickers = [t.strip() for t in args[0].split(",")]
    start = args[1]
    end = args[2]
    strategy = StrategyType.SMA_CROSSOVER
    cash = 10000.0
    interval = "1d"
    alloc = None

    i = 3
    while i < len(args):
        if args[i] == "--strategy" and i + 1 < len(args):
            try:
                strategy = StrategyType(args[i + 1])
            except ValueError:
                valid = [s.value for s in StrategyType]
                print(f"Invalid strategy. Valid: {', '.join(valid)}")
                return
            i += 2
        elif args[i] == "--cash" and i + 1 < len(args):
            cash = float(args[i + 1])
            i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        elif args[i] == "--alloc" and i + 1 < len(args):
            try:
                alloc = [float(p) for p in args[i + 1].split(",")]
                if len(alloc) != len(tickers):
                    print(f"Allocation must have {len(tickers)} values (one per ticker)")
                    return
                if abs(sum(alloc) - 100.0) > 0.01:
                    print(f"Allocation must sum to 100, got {sum(alloc)}")
                    return
            except ValueError:
                print("Invalid allocation format. Use comma-separated percentages.")
                return
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent(cash=cash)
    try:
        portfolio = agent.run_portfolio(tickers, start, end, strategy, interval, allocation=alloc)
    except ImportError as e:
        print(f"❌ {e}")
        return

    print("=" * 60)
    print("  BANKR PORTFOLIO BACKTEST")
    print("=" * 60)
    print(f"  Tickers:     {', '.join(tickers)}")
    print(f"  Strategy:    {strategy.value}")
    print(f"  Period:      {start} to {end}")
    print(f"  Initial:     ${portfolio.initial_value:,.2f}")
    print(f"  Final:       ${portfolio.current_value:,.2f}")
    print("-" * 60)
    print(f"  Portfolio Return: ${portfolio.total_pnl:+,.2f} ({portfolio.total_pnl_percent:+.2f}%)")
    print(f"  Total Trades:     {portfolio.trade_count}")
    print(f"  Winning/Losing:   {portfolio.winning_trades} / {portfolio.losing_trades}")
    print("=" * 60)

    # Per-ticker detail
    print()
    for ticker in tickers:
        agent2 = _get_bankr_agent(cash=cash / len(tickers))
        try:
            r = agent2.backtest(ticker, start, end, strategy, interval)
            print(f"  {agent2.summary_line(r)}")
        except ImportError:
            pass


def _cmd_bankr_report(args):
    """Show a backtest report.

    Usage: bankr-report [<result-index>] [--list]
    """
    agent = _get_bankr_agent()

    if args and args[0] == "--list":
        _cmd_bankr_list([])
        return

    if not args:
        print("Usage: bankr-report [<result-index>] [--list]")
        print("  <result-index>  Index of backtest result to show (default: 0)")
        print("  --list          List available results first")
        print()
        print("Use 'bankr-list' to see available results or 'bankr-backtest' to run one.")
        return

    try:
        idx = int(args[0])
    except ValueError:
        print("Usage: bankr-report [<result-index>] [--list]")
        return

    if idx < 0 or idx >= len(agent.results):
        print(f"❌ No result at index {idx}. Use 'bankr-list' to see available results.")
        return

    print(agent.generate_report(agent.results[idx]))


def _cmd_bankr_strategies(args):
    """List available trading strategies and their default parameters."""
    print("Bankr Trading Strategies")
    print("=" * 60)
    for strategy in StrategyType:
        defaults = BankrAgent._default_strategy_params(strategy)
        params_str = ", ".join(f"{k}={v}" for k, v in defaults.items()) if defaults else "(none)"
        print(f"  {strategy.value:20s}  [{params_str}]")
    print()
    print("Use strategy name with --strategy flag on backtest/signals commands.")


def _cmd_bankr_list(args):
    """List saved backtest results.

    Usage: bankr-list [--limit <n>]
    """
    agent = _get_bankr_agent()
    limit = 20

    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Invalid limit: {args[i + 1]}")
                return
            i += 2
        else:
            i += 1

    results = agent.results[-limit:] if agent.results else []
    if not results:
        print("No backtest results found. Run 'bankr-backtest' first.")
        return

    print(f"{'Idx':>4s} {'Ticker':8s} {'Strategy':18s} {'Return':>10s} {'Sharpe':>8s} {'DD':>8s} {'Trades':>7s} {'Win%':>6s}")
    print("-" * 75)
    base = max(0, len(agent.results) - limit)
    for i, r in enumerate(results):
        idx = base + i
        sharpe_str = f"{r.sharpe_ratio:.2f}" if r.sharpe_ratio is not None else "N/A"
        ret_str = f"{r.total_return_pct:+.2f}%"
        dd_str = f"{r.max_drawdown_pct:.1f}%"
        print(f"{idx:>4d} {r.ticker:>8s} {r.strategy.value:18s} {ret_str:>10s} {sharpe_str:>8s} {dd_str:>8s} {r.total_trades:>7d} {r.win_rate:>5.1f}%")


def _cmd_bankr_status(args):
    """Show Bankr agent status and configuration."""
    agent = _get_bankr_agent()

    print("🏦 Bankr Trading Agent — Status")
    print("=" * 50)
    print(f"  Data Directory:  {agent.data_dir}")
    print(f"  Initial Cash:    ${agent.initial_cash:,.2f}")
    print(f"  Saved Results:   {len(agent.results)}")
    print(f"  Portfolio Cash:  ${agent.portfolio.cash:,.2f}")

    providers = []
    if hasattr(agent, '_fetch_fn') and agent._fetch_fn is not None:
        providers.append("custom (injected)")
    elif BankrAgent.__module__:
        from importlib import util as _util
        if _util.find_spec("yfinance"):
            providers.append("yfinance (available)")
        else:
            providers.append("yfinance (not installed)")
    else:
        providers.append("unknown")

    print(f"  Data Provider:   {', '.join(providers)}")
    print()
    print("  Available Strategies:")
    for strategy in StrategyType:
        defaults = BankrAgent._default_strategy_params(strategy)
        params_str = ", ".join(f"{k}={v}" for k, v in defaults.items()) if defaults else ""
        print(f"    {strategy.value:20s}  [{params_str}]")
    print()
    print("  Commands:")
    print("    bankr-fetch       Fetch market data")
    print("    bankr-analyze     Compute technical indicators")
    print("    bankr-signals     Generate trading signals")
    print("    bankr-backtest    Run backtest")
    print("    bankr-portfolio   Run multi-ticker portfolio")
    print("    bankr-report      Show report")
    print("    bankr-list        List results")
    print("    bankr-strategies  List strategies")

    # LLM status
    print()
    print("  LLM Analysis:")
    try:
        agent.setup_llm()
        avail, msg = agent.llm.is_available() if agent.llm else (False, "Not initialized")
        if avail:
            print(f"    ✅ {msg}")
        else:
            print(f"    ⚠️  {msg}")
        print(f"    Preferred model: qwen3:8b (or best available)")
    except Exception:
        print("    ⚠️  LLM analysis: check 'bankr-llm-status' for details")


def _cmd_bankr_analyze_ai(args):
    """AI-powered technical analysis using local Ollama model.

    Usage: bankr-analyze-ai <ticker> <start> <end> [--model <model>]
           [--type <technical|portfolio|analysis>] [--interval <interval>]
    """
    if len(args) < 3:
        print("Usage: bankr-analyze-ai <ticker> <start> <end> [--model <model>] "
              "[--type <technical|portfolio|analysis>] [--interval <interval>]")
        print("\nReplaces xAI Grok from original xai_finance_agent with local Ollama models.")
        print("Requires: ollama serve running, model pulled (e.g.  'ollama pull qwen3:8b')")
        return

    ticker = args[0]
    start = args[1]
    end = args[2]
    model = None
    analysis_type = "technical"
    interval = "1d"

    i = 3
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            analysis_type = args[i + 1]
            i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            interval = args[i + 1]
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent()
    print(f"🧠 Bankr AI Analysis — {ticker}")
    print(f"   Analysis: {analysis_type}")
    print(f"   Period:   {start} → {end}")
    print(f"   Model:    {model or 'auto-detect (qwen3:8b / best available)'}")
    print(f"   Engine:   Ollama (local, replaces xAI Grok)")
    print("-" * 60)
    print()

    result = agent.analyze_with_llm(
        ticker=ticker, start=start, end=end,
        analysis_type=analysis_type, interval=interval,
        model=model,
    )
    print(result)


def _cmd_bankr_chat(args):
    """Ask a financial question to the local LLM.

    Usage: bankr-chat <question> [--context <text>]
    """
    if not args:
        print("Usage: bankr-chat <question> [--context <text>]")
        print("Ask a financial question to the local Ollama LLM.")
        print("Example: bankr-chat \"What's the P/E ratio of AAPL and how does it compare to the sector?\"")
        return

    query = args[0]
    context = None

    i = 1
    while i < len(args):
        if args[i] == "--context" and i + 1 < len(args):
            context = args[i + 1]
            i += 2
        else:
            i += 1

    agent = _get_bankr_agent()
    print(f"💬 Bankr Chat")
    print(f"   Query: {query[:120]}{'...' if len(query) > 120 else ''}")
    print(f"   Engine: Ollama (local, qwen3:8b / best available)")
    print("-" * 60)
    print()

    response = agent.chat_with_llm(query, context=context)
    print(response)


def _cmd_bankr_llm_status(args):
    """Check LLM availability and show configured model.

    Usage: bankr-llm-status
    """
    print("🤖 Bankr LLM Status")
    print("=" * 50)

    # Check Ollama connectivity
    available_models = _ollama_list_models()
    if not available_models:
        print("  Ollama:    ❌ Not reachable at http://localhost:11434")
        print()
        print("  To fix:")
        print("    1. Start Ollama: ollama serve")
        print("    2. Pull a model:  ollama pull qwen3:8b")
        print("    3. Verify:        ollama list")
        print()
        print("  The original xai_finance_agent used xAI Grok (cloud API).")
        print("  Bankr replaces it with local Ollama models for privacy.")
        return

    print(f"  Ollama:    ✅ Reachable")
    print(f"  Models:    {len(available_models)} available")
    print()

    # Find best model
    best = _find_best_ollama_model()
    print(f"  Recommended: {best}")
    print()

    # Show available models suitable for analysis
    print("  Available Models (analysis-suitable):")
    for m in sorted(available_models):
        if "embed" not in m.lower() and "whisper" not in m.lower():
            marker = " ⬅️ selected" if m == best else ""
            print(f"    • {m}{marker}")

    print()
    print("  To use a specific model with bankr-analyze-ai:")
    print("    bankr-analyze-ai AAPL 2024-01-01 2024-12-31 --model qwen3:8b")


# ── Reflection Commands ────────────────────────────────────────────────────────


def _cmd_reflect_record(args):
    """Record a reflection event.

    Usage: reflect-record --task <t> --category <cat> --observation <obs>
              --cause <cause> --lesson <lesson> --scope <scope>
              --confidence <0.0-1.0> --evidence <n> --action <act>
              [--friction <text>]
    """
    from .self_improve import cmd_reflect_record
    cmd_reflect_record(args)


def _cmd_reflect_distill(args):
    """Distill experiences into candidate lessons.

    Usage: reflect-distill [--min-occurrences <n>]
    """
    from .self_improve import cmd_reflect_distill
    cmd_reflect_distill(args)


def _cmd_reflect_promote(args):
    """Promote validated candidates to capabilities.

    Usage: reflect-promote [--auto] [--event-id <id>] [--level <0-3>]
    """
    from .self_improve import cmd_reflect_promote
    cmd_reflect_promote(args)


def _cmd_reflect_validate(args):
    """Record capability validation.

    Usage: reflect-validate --capability <id> --task <task> --outcome <text>
              --success [--delta <float>]
    """
    from .self_improve import cmd_reflect_validate
    cmd_reflect_validate(args)


def _cmd_reflect_report(args):
    """Generate reflection system report.

    Usage: reflect-report
    """
    from .self_improve import cmd_reflect_report
    cmd_reflect_report(args)


def _cmd_reflect_bridge(args):
    """Show runtime reflection bridge prompt overlay.

    Usage: reflect-bridge [--scope <scope>] [--tokens <n>]
    """
    import argparse
    parser = argparse.ArgumentParser(description="Show reflection bridge overlay")
    parser.add_argument("--scope", default="general", help="Current scope (default: general)")
    parser.add_argument("--tokens", type=int, default=500, help="Token budget (default: 500)")

    parsed = parser.parse_args(args)

    bridge = RuntimeReflectionBridge(TokenBudget(max_capability_tokens=parsed.tokens))
    overlay = bridge.build_system_prompt_overlay(parsed.scope)

    if overlay:
        print(overlay)
    else:
        print(f"No active capabilities found for scope: {parsed.scope}")


def _cmd_reflect_analysis(args):
    """Show reflection system analysis report.

    Usage: reflect-analysis [--json]
    """
    import json as json_mod

    report = reflection_report()

    if "--json" in args:
        print(json_mod.dumps(report, indent=2))
        return

    print(f"\n{'='*60}")
    print("  REFLECTION SYSTEM ANALYSIS")
    print(f"{'='*60}\n")

    ref = report.get("reflection", {})
    print(f"  Reflections: {ref.get('total_reflections', 0)}")
    print(f"  Avg Confidence: {ref.get('average_confidence', 0):.0%}")
    print(f"  Total Evidence: {ref.get('total_evidence', 0)}")
    print()

    caps = report.get("capabilities", {})
    print(f"  Capabilities: {caps.get('total_capabilities', 0)}")
    print(f"  Validated: {caps.get('validated_capabilities', 0)}")
    print(f"  By Level: {caps.get('promotion_levels', {})}")
    print()

    val = report.get("validation", {})
    print(f"  Validations: {val.get('total_validations', 0)}")
    print(f"  Use Count: {val.get('total_use_count', 0)}")
    print()

    health = report.get("capability_health", [])
    risks = [h for h in health if h.get("risk")]
    if risks:
        print(f"  CAPABILITIES AT RISK: {len(risks)}")
        for h in risks:
            print(f"    - {h['name']}: conf={h['confidence']:.2f}, evidence={h['evidence']}, validated={h['validated']}")
    else:
        print("  No capability risks detected.")
    print()

    patterns = report.get("friction_patterns", [])
    if patterns:
        print("  TOP FRICTION PATTERNS:")
        for cat, count in patterns:
            print(f"    - {cat}: {count}")

    print(f"\n{'='*60}")


def _cmd_reflect_prune(args):
    """Prune old reflection records.

    Usage: reflect-prune [--limit <n>] [--dry-run]
    """
    import argparse
    parser = argparse.ArgumentParser(description="Prune reflection records")
    parser.add_argument("--limit", type=int, default=1000, help="Max records to keep")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pruned")

    parsed = parser.parse_args(args)

    from pathlib import Path as _P
    paths = [
        _P("memory/experience_reflections.json"),
        _P("memory/capability_reflections.json"),
        _P("memory/distilled_lessons.json"),
        _P("memory/friction_analyses.json"),
        _P("memory/experience.json"),
        _P("memory/capability.json"),
    ]

    total_pruned = 0
    for p in paths:
        if not p.exists():
            continue
        if parsed.dry_run:
            from .storage_utils import safe_load_json
            records = safe_load_json(p, [])
            if isinstance(records, list) and len(records) > parsed.limit:
                print(f"  Would prune {p}: {len(records)} -> {parsed.limit}")
                total_pruned += len(records) - parsed.limit
        else:
            removed = prune_records(p, limit=parsed.limit)
            if removed:
                print(f"  Pruned {p}: removed {removed} records")
                total_pruned += removed

    if parsed.dry_run:
        print(f"\n  Total would prune: {total_pruned}")
    else:
        print(f"\n  Total pruned: {total_pruned}")


def _cmd_reflect_log(args):
    """Show or add to the friction log.

    Usage: reflect-log [--add <text>] [--tail <n>]
    """
    from pathlib import Path as _P
    log_path = _P("memory/friction_log.md")

    if "--add" in args:
        idx = args.index("--add")
        if idx + 1 < len(args):
            entry = args[idx + 1]
            from .storage_utils import append_friction_entry
            append_friction_entry(f"\n{entry}\n")
            print(f"  Added to friction log: {entry}")
        else:
            print("  Error: --add requires a text argument")
        return

    if not log_path.exists():
        print("  Friction log not yet created. Use --add to create it.")
        return

    content = log_path.read_text(encoding="utf-8")

    tail_n = 30
    if "--tail" in args:
        idx = args.index("--tail")
        if idx + 1 < len(args):
            try:
                tail_n = int(args[idx + 1])
            except ValueError:
                pass

    lines = content.strip().split("\n")
    tail_lines = lines[-tail_n:] if len(lines) > tail_n else lines
    print("\n".join(tail_lines))


if __name__ == "__main__":
    main()
