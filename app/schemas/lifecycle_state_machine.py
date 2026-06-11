from enum import Enum

class LifecycleState(Enum):
    READ = "READ"               # Record created from inbox metadata
    DOWNLOADED = "DOWNLOADED"   # Video downloaded to local_path
    CHUNKED = "CHUNKED"         # Video split, manifest created (GLM specific path)
    ANALYZED = "ANALYZED"       # LLM map/reduce finished, summary JSON saved
    COMPLETED = "COMPLETED"     # Pushed to Obsidian
    
    ANALYSIS_FAILED = "ANALYSIS_FAILED" # Catch-all terminal error state


class InvalidStateTransition(Exception):
    pass


class LifecycleStateMachine:
    """Deterministic state machine governing reel lifecycle.
    
    Valid transitions:
    READ -> DOWNLOADED
    DOWNLOADED -> CHUNKED       (GLM only)
    DOWNLOADED -> ANALYZED      (LangChain direct)
    CHUNKED -> ANALYZED         (GLM continuation)
    ANALYZED -> COMPLETED
    
    Any state -> ANALYSIS_FAILED
    """
    
    def __init__(self):
        self._valid_transitions = {
            LifecycleState.READ: {
                LifecycleState.DOWNLOADED,
                LifecycleState.ANALYSIS_FAILED
            },
            LifecycleState.DOWNLOADED: {
                LifecycleState.CHUNKED,
                LifecycleState.ANALYZED,
                LifecycleState.ANALYSIS_FAILED
            },
            LifecycleState.CHUNKED: {
                LifecycleState.ANALYZED,
                LifecycleState.ANALYSIS_FAILED
            },
            LifecycleState.ANALYZED: {
                LifecycleState.COMPLETED,
                LifecycleState.ANALYSIS_FAILED
            },
            LifecycleState.COMPLETED: set(),  # Terminal
            LifecycleState.ANALYSIS_FAILED: set(),  # Terminal
        }
        
    def validate_transition(self, current: LifecycleState, new_state: LifecycleState) -> bool:
        """Return True if transition is valid, False otherwise."""
        return new_state in self._valid_transitions.get(current, set())
        
    def transition(self, current: LifecycleState, new_state: LifecycleState) -> None:
        """Validate transition, raise InvalidStateTransition if invalid."""
        if not self.validate_transition(current, new_state):
            raise InvalidStateTransition(
                f"Cannot transition from {current.name} to {new_state.name}"
            )

LIFECYCLE_STATE_MACHINE = LifecycleStateMachine()
