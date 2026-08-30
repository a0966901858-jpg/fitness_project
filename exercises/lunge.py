from exercises.base_exercise import BaseExercise
from geometry.math_utils import MathUtils
from core.state_machine import PoseIssue
import time

class Lunge(BaseExercise):
    def __init__(self):
        super().__init__()
        # --- 狀態機與計時器參數 ---
        self.lunge_hold_start = 0
        self.is_holding = False
        self.error_timer_start = 0  # 統一在物件內部管理錯誤計時器

    def validate(self, lmList: list) -> tuple[bool, list[PoseIssue]]:
        """詳細的姿勢檢核邏輯 (保留你原本優異的幾何運算)"""
        issues = []
        l_leg = {'hip': lmList[23], 'knee': lmList[25], 'ankle': lmList[27], 'heel': lmList[29], 'toe': lmList[31]}
        r_leg = {'hip': lmList[24], 'knee': lmList[26], 'ankle': lmList[28], 'heel': lmList[30], 'toe': lmList[32]}
        
        l_knee_ang = MathUtils.get_angle(l_leg['hip'], l_leg['knee'], l_leg['ankle'])
        r_knee_ang = MathUtils.get_angle(r_leg['hip'], r_leg['knee'], r_leg['ankle']) 
        
        front_leg, back_leg = (l_leg, r_leg) if l_knee_ang < r_knee_ang else (r_leg, l_leg)
        f_ang, b_ang = (l_knee_ang, r_knee_ang) if l_knee_ang < r_knee_ang else (r_knee_ang, l_knee_ang)

        if not (70 <= f_ang <= 110):
            issues.append(PoseIssue(f"前膝彎曲未達90度 ({int(f_ang)}°)", [front_leg['hip'], front_leg['knee'], front_leg['ankle']]))
            
        if b_ang < 140:
            issues.append(PoseIssue(f"後腳未打直 ({int(b_ang)}°)", [back_leg['hip'], back_leg['knee'], back_leg['ankle']]))

        back_foot_angle = MathUtils.get_horizontal_angle(back_leg['heel'], back_leg['toe'])
        if back_foot_angle > 35:
            issues.append(PoseIssue("後腳跟浮起 (請貼地)", [back_leg['heel'], back_leg['toe']]))
            
        shoulder = lmList[11] if front_leg == l_leg else lmList[12]
        vertical_point = [front_leg['hip'][0], front_leg['hip'][1] - 100]
        trunk_angle = MathUtils.get_angle(vertical_point, front_leg['hip'], shoulder)
        if trunk_angle > 20:
            issues.append(PoseIssue(f"上半身未直立 ({int(trunk_angle)}°)", [shoulder, front_leg['hip']]))
            
        return len(issues) == 0, issues

    def process_frame(self, lmList, ai_is_processing):
        """
        [高內聚總樞紐] 接收骨架陣列，內部運算所有弓箭步的階段邏輯，並吐出 UI 渲染結果。
        """
        # 初始化回傳封包
        result = {
            'dashboard_info': "",
            'color': 'RED',
            'msg': "準備開始... (請側對鏡頭)",
            'trigger_ai': False,
            'ai_prompt_issues': "",
            'track_pts': [lmList[23], lmList[25], lmList[27]]
        }

        # 1. 取得基本判斷參數
        l_knee_ang = MathUtils.get_angle(lmList[23], lmList[25], lmList[27])
        r_knee_ang = MathUtils.get_angle(lmList[24], lmList[26], lmList[28])
        front_knee_ang = min(l_knee_ang, r_knee_ang)
        
        torso_h = abs(((lmList[11][1] + lmList[12][1]) / 2) - ((lmList[23][1] + lmList[24][1]) / 2))
        ankle_dist_x = abs(lmList[27][0] - lmList[28][0])
        
        # 寬鬆門檻：雙腳距拉開且前膝稍微彎曲 (140度)，判定已進入動作狀態
        is_in_posture = (ankle_dist_x > torso_h * 0.6) and (front_knee_ang <= 140)

        # 2. 狀態機核心邏輯
        if is_in_posture:
            is_valid, issues = self.validate(lmList)
            
            # 如果發生錯誤，將 UI 追蹤點切換到錯誤發生的部位
            if issues and hasattr(issues[0], 'pts'):
                result['track_pts'] = issues[0].pts

            if is_valid:
                # 姿勢正確：重置錯誤計時，啟動或延續「維持計時」
                self.error_timer_start = 0
                if not self.is_holding:
                    self.is_holding = True
                    self.lunge_hold_start = time.time()
                
                elapsed = int(time.time() - self.lunge_hold_start)
                if elapsed < 5:
                    result['dashboard_info'] = f"維持中: {elapsed} 秒"
                    result['color'] = 'GREEN'
                    result['msg'] = "姿勢完美！請繼續維持"
                else:
                    result['dashboard_info'] = "完成！請換邊"
                    result['color'] = 'GREEN'
                    result['msg'] = "目標達成！"
            else:
                # 姿勢錯誤：中斷「維持計時」，啟動「錯誤計時」
                self.is_holding = False
                
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
            # 尚未進入動作：重置所有計時器
            self.is_holding = False
            self.error_timer_start = 0
            result['dashboard_info'] = "請跨步下蹲進入弓箭步"
            result['color'] = 'RED'
            result['msg'] = "準備開始... (請側對鏡頭)"

        return result