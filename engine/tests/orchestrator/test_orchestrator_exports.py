def test_orchestrator_exports_importable():
    # Ensure the package exposes the expected types/classes
    from engine.core.orchestrator import (
        IPlanExecutor,
        IOrchestrator,
        Plan,
        StepPlan,
        DeterministicPlanExecutor,
        EngineOrchestrator,
    )

    # Basic sanity checks: names exist
    assert IPlanExecutor is not None
    assert IOrchestrator is not None
    assert Plan is not None
    assert StepPlan is not None
    assert DeterministicPlanExecutor is not None
    assert EngineOrchestrator is not None
