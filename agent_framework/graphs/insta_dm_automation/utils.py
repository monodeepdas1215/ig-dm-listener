from agent_framework.schemas.state import PipelineStatus

def compute_pipeline_status(total: int, succeeded: int) -> PipelineStatus:
    if succeeded == 0:
        return PipelineStatus.FAILURE
    elif succeeded < total:
        return PipelineStatus.PARTIAL_SUCCESS
    else:
        return PipelineStatus.SUCCESS
