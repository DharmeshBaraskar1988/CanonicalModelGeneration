from canonical_model_generator.workflow_progress import reached_stage_count


def test_workflow_progress_counts_partial_and_current_stages_as_reached() -> None:
    assert reached_stage_count(["Complete", "Ready", "Locked", "Ready"]) == 1
    assert reached_stage_count(["Complete", "Complete", "Partial", "Ready"]) == 3
    assert reached_stage_count(["Complete", "Complete", "Complete", "Current"]) == 4
