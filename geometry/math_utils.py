# geometry/math_utils.py
import math

class MathUtils:
    @staticmethod
    def get_angle(p1, p2, p3) -> float:
        """計算三點構成的角度 (p2 為頂點)"""
        angle = math.degrees(
            math.atan2(p3[1] - p2[1], p3[0] - p2[0]) - 
            math.atan2(p1[1] - p2[1], p1[0] - p2[0])
        )
        angle = angle + 360 if angle < 0 else angle
        return 360 - angle if angle > 180 else angle

    @staticmethod
    def get_horizontal_angle(p1, p2) -> float:
        """計算兩點與水平線的夾角"""
        dx = abs(p1[0] - p2[0])
        dy = abs(p1[1] - p2[1])
        if dx == 0: return 90.0
        return math.degrees(math.atan2(dy, dx))