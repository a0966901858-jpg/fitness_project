# core/state_machine.py
from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple

class UIState(Enum):
    RED = (0, 0, 255)
    YELLOW = (0, 255, 255)
    GREEN = (0, 255, 0)

class ExerciseState(Enum):
    IDLE = auto()
    DOWN = auto()
    UP = auto()
    HOLDING = auto()
    COMPLETED = auto()

@dataclass
class PoseIssue:
    msg: str
    pts: list

@dataclass
class FeedbackState:
    text: str = "準備開始，請擺出動作..."
    color: Tuple[int, int, int] = UIState.RED.value
    state: UIState = UIState.RED