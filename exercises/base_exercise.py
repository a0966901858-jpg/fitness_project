# exercises/base_exercise.py
from abc import ABC, abstractmethod
from typing import Tuple, List
from core.state_machine import ExerciseState, PoseIssue
from configs.settings import SystemConfig

class BaseExercise(ABC):
    def __init__(self):
        self.count = 0
        self.state = ExerciseState.IDLE
        self.failure_streak = 0
        self.has_analyzed_this_rep = False
        
    @abstractmethod
    def validate(self, lmList: list) -> Tuple[bool, List[PoseIssue]]:
        """幾何規則驗證，必須由子類別實作"""
        pass
        
    def check_trigger_ai(self) -> bool:
        """判斷是否達到觸發 VLM 的條件"""
        if not self.has_analyzed_this_rep:
            self.failure_streak += 1
            self.has_analyzed_this_rep = True
            
            if self.failure_streak >= SystemConfig.FAILURE_TRIGGER_COUNT:
                self.failure_streak = 0  # 重置
                return True
        return False
        
    def reset_streak(self):
        self.failure_streak = 0