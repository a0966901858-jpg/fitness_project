import base64
import json
import re
import queue
import cv2  # 確保 OpenCV 有被引入來處理影像編碼
import ollama
from configs.settings import SystemConfig

class VLMPipeline:
    def __init__(self):
        self.request_queue = queue.Queue(maxsize=1)
        self.result_queue = queue.Queue()
        
    def worker_loop(self):
        while True:
            data = self.request_queue.get()
            if data is None: break 
            
            try:
                print("\n🤖 [VLM 執行緒] 收到錯誤動作畫面，開始請求 Ollama 分析...")
                # 將影像編碼為 JPG 以節省傳輸頻寬
                _, buffer = cv2.imencode('.jpg', data['image'])
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                
                response = ollama.chat(
                    model=SystemConfig.VLM_MODEL, 
                    messages=[{'role': 'user', 'content': data['prompt'], 'images': [img_base64]}],
                    options={'temperature': 0.0}
                )
                
                raw_result = response['message']['content']
                print(f"🤖 [VLM 執行緒] 模型原始回覆:\n{raw_result}\n")
                
                # 清洗 JSON 格式
                clean_result = raw_result.replace('```json', '').replace('```', '').strip()
                json_match = re.search(r'\{.*\}', clean_result, re.DOTALL)
                
                result = json.loads(json_match.group(0)) if json_match else json.loads(clean_result)
                self.result_queue.put({"success": True, "data": result})
                
            except json.JSONDecodeError:
                print("❌ [VLM 執行緒] 錯誤：模型沒有回傳正確的 JSON 格式")
                self.result_queue.put({
                    "success": False, 
                    "error": "AI 輸出格式異常，請重試"
                })
            except Exception as e:
                print(f"❌ [VLM 執行緒] 嚴重崩潰: {e}")
                self.result_queue.put({
                    "success": False, 
                    "error": "系統診斷連線異常"
                })
            finally:
                self.request_queue.task_done()