from exercises.base_exercise import BaseExercise
from geometry.math_utils import MathUtils
from core.state_machine import PoseIssue
import time

class Plank(BaseExercise):
    def __init__(self):
        super().__init__()
        # --- 狀態機與計時器參數 ---
        self.accumulated_time = 0.0
        self.last_tick = 0.0
        self.is_planking = False
        self.error_timer_start = 0  # 統一在物件內部管理錯誤計時器

    def validate(self, lmList: list) -> tuple[bool, list[PoseIssue]]:
        """保留原本的幾何檢核邏輯"""
        issues = []
        shoulder, elbow = lmList[12], lmList[14]
        hip, knee, ankle = lmList[24], lmList[26], lmList[28]
        
        body_angle = MathUtils.get_angle(shoulder, hip, ankle)
        if body_angle < 150:
            issues.append(PoseIssue("核心未收緊(塌腰/翹臀)", [shoulder, hip, ankle]))

        knee_angle = MathUtils.get_angle(hip, knee, ankle)
        if knee_angle < 165:
            issues.append(PoseIssue("膝蓋彎曲 (請打直雙腿)", [hip, knee, ankle]))
            
        vertical_point = [elbow[0], elbow[1] - 100]
        arm_alignment = MathUtils.get_angle(vertical_point, elbow, shoulder)
        if arm_alignment > 15:
            issues.append(PoseIssue("手肘未垂直於肩膀下方", [shoulder, elbow]))
            
        return len(issues) == 0, issues

    def process_frame(self, lmList, ai_is_processing):
        """
        [高內聚總樞紐] 接收骨架陣列，內部運算棒式的階段邏輯，並吐出 UI 渲染結果。
        """
        # 初始化回傳封包
        result = {
            'dashboard_info': "",
            'color': 'RED',
            'msg': "準備開始... (請側對鏡頭)",
            'trigger_ai': False,
            'ai_prompt_issues': "",
            'track_pts': [lmList[12], lmList[24], lmList[28]]
        }

        # 1. 取得基本判斷參數：身體的高度差與寬度差
        body_h_diff = abs(lmList[11][1] - lmList[27][1])
        body_w_diff = abs(lmList[11][0] - lmList[27][0])
        
        # 寬鬆門檻：身體高度差不大於寬度差的 80%，判定為進入趴姿
        is_in_posture = body_h_diff < body_w_diff * 0.8

        # 2. 狀態機核心邏輯
        if is_in_posture:
            is_valid, issues = self.validate(lmList)
            
            # 若發生錯誤，動態將追蹤點鎖定在錯誤部位
            if issues and hasattr(issues[0], 'pts'):
                result['track_pts'] = issues[0].pts

            if is_valid:
                # 姿勢正確：重置錯誤計時，延續目標計時
                self.error_timer_start = 0
                
                if not self.is_planking:
                    self.is_planking = True
                    self.last_tick = time.time()

                current_time = time.time()
                self.accumulated_time += (current_time - self.last_tick)
                self.last_tick = current_time
                
                remain = max(0, 60 - int(self.accumulated_time))
                
                if remain > 0:
                    result['dashboard_info'] = f"棒式倒數: {remain} 秒"
                    result['color'] = 'GREEN'
                    result['msg'] = "核心收緊，棒式維持中！"
                else:
                    result['dashboard_info'] = "目標達成！太棒了！"
                    result['color'] = 'GREEN'
                    result['msg'] = "恭喜完成 60 秒棒式！"
            else:
                # 姿勢錯誤：中斷目標計時，啟動錯誤計時
                self.is_planking = False # 確保下次綠燈時，last_tick 會重新刷新
                
                if self.error_timer_start == 0:
                    self.error_timer_start = time.time()
                    
                elapsed_error = time.time() - self.error_timer_start
                remain_sec = max(0, 5 - int(elapsed_error))
                
                result['color'] = 'YELLOW'
                
                if ai_is_processing:
                    result['msg'] = f"❌ {issues[0].msg}\n(⏳ AI 正在診斷...)"
                else:
                    result['msg'] = f"❌ {issues[0].msg}\n(矯正中... {remain_sec}秒後啟動 AI)"

                # 倒數 5 秒後觸發 AI
                if elapsed_error >= 5.0 and not ai_is_processing:
                    result['trigger_ai'] = True
                    result['ai_prompt_issues'] = ", ".join([iss.msg for iss in issues])
                    self.error_timer_start = 0
        else:
            # 尚未進入動作 (例如站立)：重置所有計時器
            self.is_planking = False
            self.error_timer_start = 0
            self.accumulated_time = 0.0 # 離開棒式姿態就歸零重來，符合嚴格訓練標準
            result['dashboard_info'] = "請撐起進入棒式"
            result['color'] = 'RED'
            result['msg'] = "準備開始... (請側對鏡頭)"

        return result