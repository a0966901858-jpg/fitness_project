# configs/settings.py

class SystemConfig:
    # 視覺與攝影機
    CAMERA_ID = 1
    WINDOW_WIDTH = 1280
    WINDOW_HEIGHT = 720
    
    # 系統 AI 設定
    VLM_MODEL = 'llava'
    FAILURE_TRIGGER_COUNT = 2  # 連續失敗幾次觸發 VLM
    VLM_TIMEOUT_SEC = 15.0     # AI 推論超時設定
    
class ExerciseConfig:
    # 深蹲參數
    SQUAT_DOWN_ANGLE = 115
    SQUAT_UP_ANGLE = 160
    SQUAT_FOOT_MAX_ANGLE = 35
    SQUAT_TRUNK_MAX_ANGLE = 35
    SQUAT_KNEE_ANKLE_RATIO = 0.9
