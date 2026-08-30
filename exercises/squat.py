import math
import time
from core.state_machine import ExerciseState

class Issue:
    def __init__(self, msg):
        self.msg = msg

class Squat:
    def __init__(self):
        self.count = 0
        self.state = ExerciseState.UP
        
        # --- 封裝狀態機參數 ---
        self.hit_target_depth = False  # 是否已達到完美深度的「綠卡」
        self.error_timer_start = 0     # 統一由物件內部管理錯誤計時器

    def _calculate_angle(self, p1, p2, p3):
        """計算三個關節點的幾何夾角"""
        x1, y1 = p1[:2]
        x2, y2 = p2[:2]
        x3, y3 = p3[:2]
        angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2))
        angle = abs(angle)
        if angle > 180:
            angle = 360 - angle
        return angle

    def _get_active_leg(self, lmList):
        """
        [核心過濾] Z 軸深度判斷：只擷取「靠近鏡頭」的該側肢體，徹底消除遮擋晃動。
        MediaPipe 中 Z 值越小（越負）代表離攝影機越近。
        """
        is_left_closer = lmList[23][2] < lmList[24][2]
        
        if is_left_closer:
            shoulder = lmList[11]
            hip = lmList[23]
            knee = lmList[25]
            ankle = lmList[27]
        else:
            shoulder = lmList[12]
            hip = lmList[24]
            knee = lmList[26]
            ankle = lmList[28]
            
        return shoulder, hip, knee, ankle

    def process_frame(self, lmList, ai_is_processing):
        """
        [高內聚總樞紐] 接收骨架陣列，內部運算所有幾何與時間邏輯，並直接吐出給 UI 的渲染結果。
        """
        # 1. 取得近側腳座標與膝蓋夾角
        shoulder, hip, knee, ankle = self._get_active_leg(lmList)
        angle = self._calculate_angle(hip, knee, ankle)
        
        hip_y = hip[1]
        knee_y = knee[1]
        
        # 2. 幾何區間判定
        is_parallel = -20 <= (knee_y - hip_y) <= 20
        is_good_angle = 55 <= angle <= 155
        is_too_deep = angle < 55 or (knee_y - hip_y) < -20
        is_standing = angle >= 160

        # 3. 初始化回傳封包
        result = {
            'dashboard_info': f"深蹲次數: {self.count}",
            'color': 'RED',
            'msg': "準備開始... (請側對鏡頭)",
            'trigger_ai': False,
            'ai_prompt_issues': "",
            'track_pts': [hip, knee, ankle]
        }

        # 4. 狀態機核心邏輯
        if is_standing:
            # 站立時結算上一回的次數
            if self.hit_target_depth:
                self.count += 1
                result['dashboard_info'] = f"深蹲次數: {self.count}"
            
            # 狀態重置
            self.hit_target_depth = False
            self.state = ExerciseState.UP
            self.error_timer_start = 0 
            
        elif angle <= 140:
            self.state = ExerciseState.DOWN
            
            # TODO: 未來可在此處加入背部是否挺直的 validate_posture 邏輯
            is_valid = True 
            issues_msg = ""
            
            # 已獲得綠卡
            if self.hit_target_depth:
                if is_too_deep:
                    self.hit_target_depth = False  # 剝奪綠卡
                    result['color'] = 'YELLOW'
                    result['msg'] = "⚠️ 蹲太低了！請稍微抬高臀部"
                    issues_msg = "蹲太低，臀部低於膝蓋"
                else:
                    result['color'] = 'GREEN'
                    result['msg'] = "完美深度！請保持並站起"
                    self.error_timer_start = 0
                    
            # 尚未獲得綠卡，但姿態達標
            elif is_valid and is_parallel and is_good_angle:
                self.hit_target_depth = True  # 頒發綠卡
                result['color'] = 'GREEN'
                result['msg'] = "完美深度！請保持並站起"
                self.error_timer_start = 0
                
            # 尚未達標，進入黃燈矯正期
            else:
                if not is_valid:
                    msg = issues_msg
                elif is_too_deep:
                    msg = "蹲太低了！臀部不可低於膝蓋"
                    issues_msg = msg
                elif angle > 110:
                    msg = "請繼續下蹲至大腿與地面平行"
                    issues_msg = msg
                else:
                    msg = "請微調姿勢，保持重心穩定"
                    issues_msg = msg

                if self.error_timer_start == 0:
                    self.error_timer_start = time.time()
                    
                elapsed = time.time() - self.error_timer_start
                remain_sec = max(0, 5 - int(elapsed))
                
                result['color'] = 'YELLOW'
                
                if ai_is_processing:
                    result['msg'] = f"❌ {msg}\n(⏳ AI 正在診斷...)"
                else:
                    result['msg'] = f"❌ {msg}\n(矯正中... {remain_sec}秒後啟動 AI)"
                
                # 倒數 5 秒觸發 AI
                if elapsed >= 5.0 and not ai_is_processing:
                    result['trigger_ai'] = True
                    result['ai_prompt_issues'] = issues_msg
                    self.error_timer_start = 0

        return result