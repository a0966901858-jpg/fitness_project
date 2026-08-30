'''
cd ~/Documents/fitness_project
conda activate fitness_coach
python main.py
'''
import cv2
import threading
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO
import mediapipe as mp

from configs.settings import SystemConfig
from core.state_machine import UIState, FeedbackState, ExerciseState
from exercises.squat import Squat
from exercises.lunge import Lunge
from exercises.plank import Plank
from ai.vlm_pipeline import VLMPipeline

# ==========================================
# 視覺與追蹤工具
# ==========================================
class TopDownPoseDetector:
    def __init__(self):
        print("正在載入 YOLOv8 模型...")
        self.yolo_model = YOLO('yolov8n.pt')
        self.mp_pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.pose_connections = mp.solutions.pose.POSE_CONNECTIONS

    def find_pose(self, img, draw=True):
        h, w, _ = img.shape
        pose_info = None
        results = self.yolo_model(img, classes=0, verbose=False)
        if results and len(results[0].boxes) > 0:
            box = results[0].boxes[0].xyxy[0].cpu().numpy()
            pad = 30
            x1, y1 = max(0, int(box[0]) - pad), max(0, int(box[1]) - pad)
            x2, y2 = min(w, int(box[2]) + pad), min(h, int(box[3]) + pad)
            crop_img = img[y1:y2, x1:x2]
            
            if crop_img.shape[0] > 0 and crop_img.shape[1] > 0:
                mp_results = self.mp_pose.process(cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB))
                mylmList = []
                if mp_results.pose_landmarks:
                    for id, lm in enumerate(mp_results.pose_landmarks.landmark):
                        cx, cy = int(lm.x * crop_img.shape[1]) + x1, int(lm.y * crop_img.shape[0]) + y1
                        mylmList.append([cx, cy, lm.z])
                    pose_info = {"lmList": mylmList}
                    if draw:
                        # 畫骨架連線
                        for connection in self.pose_connections:
                            cv2.line(img, tuple(mylmList[connection[0]][:2]), tuple(mylmList[connection[1]][:2]), (255, 255, 255), 2)
                        # 畫關節點
                        for pt in mylmList: cv2.circle(img, tuple(pt[:2]), 4, (0, 0, 255), cv2.FILLED)
        return pose_info, img

def put_chinese_text(img, text, position, text_color=(0, 255, 0), font_size=30):
    try:
        pil_im = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_im)
        font_paths = ["msjh.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "NotoSansCJK-Regular.ttc"]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size, encoding="utf-8")
                break 
            except IOError: continue
        if font is None: font = ImageFont.load_default()
        draw.text(position, text, font=font, fill=text_color)
        return cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
    except Exception:
        cv2.putText(img, str(text), position, cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2)
        return img

# ==========================================
# 主流程 (Orchestrator)
# ==========================================
def main():
    cap = cv2.VideoCapture(SystemConfig.CAMERA_ID)
    detector = TopDownPoseDetector()
    
    cv2.namedWindow("Smart Fitness Mirror", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Smart Fitness Mirror", 1280, 720)
    
    ai_pipeline = VLMPipeline()
    threading.Thread(target=ai_pipeline.worker_loop, daemon=True).start()
    
    # 狀態管理器
    current_mode_name = 'SQUAT'
    exercise_instances = {
        'SQUAT': Squat(),
        'LUNGE': Lunge(),
        'PLANK': Plank()
    }
    current_exercise = exercise_instances[current_mode_name]
    
    ai_is_processing = False
    ai_advice_text = ""
    ai_advice_expiry = 0
    
    # 保留預設 feedback，防止沒有偵測到骨架時發生 UnboundLocalError
    feedback = FeedbackState("等待偵測中...", UIState.YELLOW.value, UIState.YELLOW)

    DIAGNOSTIC_PROMPT = """# 角色設定
你是嚴格且專注於「當下即時矯正」的 AI 健身教練。
絕對禁止提供長期訓練規劃、醫療建議或無意義的廢話。

# 當前動作
{action}

# 系統已偵測到的幾何錯誤
{known_issues}

# 你的任務
觀察圖片中錯誤的關節與肢體位置。使用者現在正卡在這個錯誤姿勢中，你必須給出能讓他「在 3 秒內立刻照著做」的具體物理微調指令。
絕對禁止提及「活動度不足」、「增加運動頻率」、「尋求專業教練」、「長期練習」等空泛建議。

# 輸出規則 (極度重要)
1. 必須是純 JSON 格式，絕對禁止在 JSON 外附加任何文字。
2. 語氣要像真實教練在旁邊下指令，極度精簡、口語、一針見血。
{{"root_cause": "<15字以內，說明當下哪個身體部位擺錯了，例如：屁股翹太高、後腳跟沒有往後蹬直>", "actionable_advice": "<25字以內，給出一個具體的肌肉控制口令，例如：請將骨盆往下壓讓背部打平，用力收緊核心！>"}}"""

    while True:
        success, img = cap.read()
        if not success: break

        # 1. 處理 AI 非同步回傳
        if not ai_pipeline.result_queue.empty():
            res = ai_pipeline.result_queue.get()
            ai_is_processing = False 
            if res['success']:
                cause = res['data'].get("root_cause", "姿勢發力不對")
                adv = res['data'].get("actionable_advice", "請調整重心")
                ai_advice_text = f"💡 AI 診斷: {adv} ({cause})"
                ai_advice_expiry = time.time() + 8.0 
            else:
                ai_advice_text = f"⚠️ AI 診斷連線異常"
                ai_advice_expiry = time.time() + 3.0

        pose, img = detector.find_pose(img, draw=True)
        dashboard_info = ""

        # 2. 核心邏輯
        if pose:
            lmList = pose["lmList"]
            mode_tw = {"SQUAT": "深蹲", "LUNGE": "弓箭步", "PLANK": "棒式"}[current_mode_name]

            # --- 自動偵測切換模式 ---
            can_switch = (
                (current_mode_name == 'SQUAT' and getattr(current_exercise, 'state', None) != ExerciseState.DOWN) or
                (current_mode_name == 'LUNGE' and not getattr(current_exercise, 'is_holding', False)) or
                (current_mode_name == 'PLANK' and not getattr(current_exercise, 'is_planking', False))
            )

            if can_switch:
                sx, sy = (lmList[11][0] + lmList[12][0]) / 2, (lmList[11][1] + lmList[12][1]) / 2
                hx, hy = (lmList[23][0] + lmList[24][0]) / 2, (lmList[23][1] + lmList[24][1]) / 2
                ax, ay = (lmList[27][0] + lmList[28][0]) / 2, (lmList[27][1] + lmList[28][1]) / 2
                
                body_w, body_h, torso_h = abs(sx - ax), abs(sy - ay), abs(sy - hy)
                ankle_dist_x = abs(lmList[27][0] - lmList[28][0])

                detected_mode = 'SQUAT'
                if body_w > body_h * 1.2: detected_mode = 'PLANK'
                elif ankle_dist_x > torso_h * 1.1: detected_mode = 'LUNGE'

                if detected_mode != current_mode_name:
                    current_mode_name = detected_mode
                    current_exercise = exercise_instances[current_mode_name]
                    feedback = FeedbackState("切換模式，準備開始... (請側對鏡頭)", UIState.RED.value, UIState.RED)
            
            # ====================================================================
            # 💡 [重構威力展現] 統一呼叫，消滅所有 if-else 邏輯迷宮
            # ====================================================================
            result = current_exercise.process_frame(lmList, ai_is_processing)
            
            dashboard_info = result['dashboard_info']
            
            # 對應 UI 顏色
            color_map = {
                'RED': UIState.RED.value,
                'YELLOW': UIState.YELLOW.value,
                'GREEN': UIState.GREEN.value
            }
            ui_color = color_map.get(result['color'], UIState.RED.value)
            feedback = FeedbackState(result['msg'], ui_color, ui_color)

            # 動態畫出錯誤部位的追蹤點 (用黃圈特別標示)
            if result.get('track_pts'):
                for pt in result['track_pts']:
                    cv2.circle(img, tuple(pt[:2]), 10, (0, 255, 255), 2)
                    cv2.circle(img, tuple(pt[:2]), 5, (0, 0, 255), cv2.FILLED)

            # 觸發 AI 診斷
            if result['trigger_ai'] and not ai_is_processing:
                ai_is_processing = True
                ai_pipeline.request_queue.put({
                    'image': img.copy(),
                    'prompt': DIAGNOSTIC_PROMPT.format(action=mode_tw, known_issues=result['ai_prompt_issues'])
                })
            # ====================================================================

        # 3. 儀表板 UI 渲染
        # (這裡若 pose 不存在，會直接使用預設或上一幀保留的 feedback 與 dashboard_info)
        mode_tw_display = {"SQUAT": "深蹲", "LUNGE": "弓箭步", "PLANK": "棒式"}.get(current_mode_name, "深蹲")
        img = put_chinese_text(img, f"[自動切換] {mode_tw_display}模式", (30, 40), (255, 165, 0), 35)
        cv2.circle(img, (50, 100), 20, feedback.color, cv2.FILLED)
        
        if dashboard_info:
            img = put_chinese_text(img, dashboard_info, (30, 130), (0,0,0), 40)
        
        lines = feedback.text.split('\n')
        y_offset = 180
        for line in lines:
            img = put_chinese_text(img, line, (30, y_offset), feedback.color, 35)
            y_offset += 50

        # ----------------------------------------------------
        # 動態寬度字幕模式 (解決溢出、方塊與顏色問題)
        # ----------------------------------------------------
        if time.time() < ai_advice_expiry:
            font_size = 28
            line_height = 40
            
            max_chars = max(15, (img.shape[1] - 80) // font_size) 
            wrapped_lines = []
            
            clean_text = ai_advice_text.replace('\n', ' ').replace('💡', '').replace('❌', '').replace('⚠️', '').strip()
            
            for i in range(0, len(clean_text), max_chars):
                wrapped_lines.append(clean_text[i:i+max_chars])
            
            box_height = len(wrapped_lines) * line_height + 20
            start_y = img.shape[0] - box_height

            overlay = img.copy()
            cv2.rectangle(overlay, (0, start_y), (img.shape[1], img.shape[0]), (0, 0, 0), cv2.FILLED)
            cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)

            text_y = start_y + 10
            for line in wrapped_lines:
                img = put_chinese_text(img, line, (40, text_y), (255, 165, 0), font_size)
                text_y += line_height

        cv2.imshow("Smart Fitness Mirror", img)
        if cv2.waitKey(1) & 0xFF == ord("q"): break

    ai_pipeline.request_queue.put(None)
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
