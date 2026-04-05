from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
import subprocess
import os
import sys
import time
import shutil
import threading
from datetime import datetime
import traceback
import dropbox
from dropbox.exceptions import AuthError, ApiError
import glob 
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

# ================= 網站安全設定 =================
# 必須設定 Secret Key 才能使用 session (通行證) 功能
app.secret_key = 'change_this_to_any_random_secret_string' 

# 在這裡設定允許登入的帳號與密碼 (格式: {"帳號": "密碼"})
AUTHORIZED_USERS = {
    "admin": "YOUR_SECURE_PASSWORD"    # 你可以隨意新增多組帳號
}
# =================================================

# ================= 備份與伺服器設定 =================
DROPBOX_APP_KEY = 'YOUR_DROPBOX_APP_KEY'        
DROPBOX_APP_SECRET = 'YOUR_DROPBOX_APP_SECRET'     
DROPBOX_REFRESH_TOKEN = 'YOUR_DROPBOX_REFRESH_TOKEN' 
# =================================================
MAX_BACKUPS = 7                             # 要保留的世界存檔數量
JAVA_DIR = os.path.dirname(os.path.abspath(__file__)) # 伺服器根目錄
WORLD_DIR = os.path.join(JAVA_DIR, 'world') # 世界存檔的資料夾
BACKUP_TEMP_DIR = JAVA_DIR      # 壓縮檔暫存位置
# =================================================

server_process = None

# 全域狀態 (用來讓前端進度條讀取)
state = {
    "is_running": False,   
    "action": "idle",      
    "progress": 0,         
    "message": "系統待命中...",
    "log_pos": 0 
}

# 登入頁面 HTML
LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>伺服器登入</title>
    <style>
        body { font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; background-color: #2c3e50; margin: 0; }
        .login-box { background: #34495e; padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); text-align: center; color: white; width: 300px; }
        h2 { margin-top: 0; margin-bottom: 20px; }
        input { display: block; width: 100%; margin: 15px 0; padding: 12px; border-radius: 5px; border: none; font-size: 16px; box-sizing: border-box; background-color: #ecf0f1;}
        button { background-color: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 18px; border-radius: 5px; cursor: pointer; width: 100%; transition: 0.3s; font-weight: bold;}
        button:hover { background-color: #2ecc71; }
        .error { color: #e74c3c; font-weight: bold; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>伺服器控制台</h2>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST" action="/login">
            <input type="text" name="username" placeholder="使用者帳號" required autocomplete="off">
            <input type="password" name="password" placeholder="登入密碼" required>
            <button type="submit">安全登入</button>
        </form>
    </div>
</body>
</html>
"""

# 主控台 HTML (新增了登出按鈕)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>伺服器控制面板</title>
    <style>
        body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #2c3e50; margin: 0; position: relative;}
        .logout-btn { position: absolute; top: 20px; right: 20px; padding: 10px 20px; font-size: 16px; font-weight: bold; cursor: pointer; background-color: #e74c3c; color: white; border: none; border-radius: 8px; transition: 0.3s; text-decoration: none;}
        .logout-btn:hover { background-color: #c0392b; }
        .btn-container { display: flex; gap: 20px; }
        button.action-btn { padding: 20px 40px; font-size: 24px; font-weight: bold; cursor: pointer; color: white; border: none; border-radius: 10px; transition: 0.3s; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
        #startButton { background-color: #27ae60; }
        #startButton:hover { background-color: #2ecc71; }
        #stopButton { background-color: #c0392b; }
        #stopButton:hover { background-color: #e74c3c; }
        button.action-btn:disabled { background-color: #95a5a6 !important; cursor: not-allowed; box-shadow: none;}
        #status-box { margin-top: 30px; background: #34495e; padding: 25px; border-radius: 8px; width: 80%; max-width: 600px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
        #status-text { font-size: 18px; color: #ecf0f1; white-space: pre-wrap; line-height: 1.5; font-weight: bold; text-align: center;}
        #progress-container { width: 100%; background-color: #1a252f; border-radius: 10px; margin-top: 15px; overflow: hidden; display: none; height: 25px;}
        #progress-bar { height: 100%; width: 0%; background-color: #3498db; transition: width 0.5s ease; }
    </style>
</head>
<body>
    <a href="/logout" class="logout-btn">登出系統</a>

    <div class="btn-container">
        <button id="startButton" class="action-btn" onclick="sendCommand('/start')" disabled>啟動伺服器</button>
        <button id="stopButton" class="action-btn" onclick="sendCommand('/stop')" disabled>關閉與備份</button>
    </div>
    
    <div id="status-box">
        <div id="status-text">連線中...</div>
        <div id="progress-container">
            <div id="progress-bar"></div>
        </div>
    </div>

    <script>
        async function sendCommand(endpoint) {
            if (endpoint === '/stop' && !confirm("確定要關閉伺服器並執行備份嗎？")) return;
            try { 
                const res = await fetch(endpoint, { method: 'POST' }); 
                if (res.status === 401) window.location.href = '/login'; 
            } 
            catch (e) { console.error("指令發送失敗", e); }
        }

        setInterval(async () => {
            try {
                const res = await fetch('/status');
                if (res.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                const data = await res.json();
                
                document.getElementById('status-text').innerText = data.message;
                
                const progContainer = document.getElementById('progress-container');
                const progBar = document.getElementById('progress-bar');
                if (data.progress > 0 && data.action !== 'idle') {
                    progContainer.style.display = 'block';
                    progBar.style.width = data.progress + '%';
                } else {
                    progContainer.style.display = 'none';
                }
                
                const startBtn = document.getElementById('startButton');
                const stopBtn = document.getElementById('stopButton');
                if (data.action !== 'idle' || data.action === 'stopping') {
                    startBtn.disabled = true; stopBtn.disabled = true;
                } else {
                    startBtn.disabled = data.is_running;
                    stopBtn.disabled = !data.is_running;
                }
            } catch (e) {
                document.getElementById('status-text').innerText = "⚠️ 與控制面板失去連線...";
            }
        }, 1000);
    </script>
</body>
</html>
"""

def check_screen_running():
    global server_process
    if server_process is not None:
        return server_process.poll() is None
    return False

def cleanup_temp_zips():
    try:
        search_pattern = os.path.join(BACKUP_TEMP_DIR, "world_backup_*.zip")
        leftover_files = glob.glob(search_pattern)
        for old_zip in leftover_files:
            os.remove(old_zip)
            print(f"[清理系統] 已刪除意外殘留的暫存壓縮檔: {old_zip}")
    except Exception as e:
        print(f"[⚠️ 警告] 清理殘留檔案失敗: {e}")

def perform_backup():
    global state
    state["action"] = "backing_up"
    zip_full_path = None
    
    cleanup_temp_zips()
    
    try:
        print("[後端系統] 開始執行備份與壓縮程序...")
        state["message"] = "📦 正在壓縮世界檔案..."
        state["progress"] = 20
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"world_backup_{timestamp}"
        zip_path = os.path.join(BACKUP_TEMP_DIR, zip_filename)
        shutil.make_archive(zip_path, 'zip', WORLD_DIR)
        zip_full_path = f"{zip_path}.zip"
        
        print(f"[後端系統] 壓縮完成，準備上傳至 Dropbox: {zip_full_path}")
        state["message"] = "☁️ 正在上傳至 Dropbox (大檔案分塊傳輸中)..."
        state["progress"] = 50
        
        if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
            dbx = dropbox.Dropbox(
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
            )
        else:
            print("[⚠️ 警告] 尚未設定 Refresh Token，將使用可能已過期的舊 Token！")
            dbx = dropbox.Dropbox(DROPBOX_TOKEN_EXPIRED)

        file_size = os.path.getsize(zip_full_path)
        CHUNK_SIZE = 8 * 1024 * 1024  
        
        with open(zip_full_path, 'rb') as f:
            if file_size <= 100 * 1024 * 1024:
                dbx.files_upload(f.read(), f"/{zip_filename}.zip", mode=dropbox.files.WriteMode.overwrite)
            else:
                upload_session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
                cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id, offset=f.tell())
                commit = dropbox.files.CommitInfo(path=f"/{zip_filename}.zip", mode=dropbox.files.WriteMode.overwrite)

                while f.tell() < file_size:
                    if (file_size - f.tell()) <= CHUNK_SIZE:
                        dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
                    else:
                        dbx.files_upload_session_append_v2(f.read(CHUNK_SIZE), cursor)
                        cursor.offset = f.tell()
        
        print("[後端系統] 上傳成功，正在檢查並清理雲端舊備份...")
        state["message"] = "🧹 正在清理雲端舊備份..."
        state["progress"] = 80
        result = dbx.files_list_folder('')
        files = [e for e in result.entries if isinstance(e, dropbox.files.FileMetadata)]
        files.sort(key=lambda x: x.server_modified)
        
        while len(files) > MAX_BACKUPS:
            dbx.files_delete_v2(files.pop(0).path_lower)
            
        print("[後端系統] ✅ 備份流程完美結束！")
        state["message"] = f"✅ 備份完成！({zip_filename}.zip)\n系統已進入待命狀態。"
        state["progress"] = 100
        time.sleep(4) 
        
    except AuthError as e:
        error_msg = "Dropbox Token 驗證失敗。請確認您是否已正確設定 App Key, Secret 與 Refresh Token。"
        print(f"\n[❌ 後端報錯 - 授權失敗] {error_msg}")
        traceback.print_exc()
        state["message"] = f"❌ 備份失敗: {error_msg}"
        time.sleep(10)
    except ApiError as e:
        error_msg = f"Dropbox API 拒絕請求。\n詳細錯誤: {e}"
        print(f"\n[❌ 後端報錯 - API 錯誤] {error_msg}")
        traceback.print_exc()
        state["message"] = f"❌ 備份失敗: API錯誤"
        time.sleep(10)
    except Exception as e:
        error_msg = f"發生未知的系統或網路錯誤: {str(e)}"
        print(f"\n[❌ 後端報錯 - 系統錯誤] {error_msg}")
        traceback.print_exc()
        state["message"] = f"❌ 備份失敗: 系統錯誤"
        time.sleep(10)
    finally:
        if zip_full_path and os.path.exists(zip_full_path):
            try:
                os.remove(zip_full_path)
                print(f"[後端系統] 已清理本地暫存壓縮檔: {zip_full_path}")
            except Exception as e:
                print(f"[⚠️ 警告] 無法刪除本地暫存檔: {str(e)}")
                
        state["action"] = "idle"
        state["progress"] = 0
        if not check_screen_running():
            state["message"] = "系統待命中..."

def server_monitor():
    global state
    log_path = os.path.join(JAVA_DIR, 'console_output.log')

    while True:
        time.sleep(10)
        is_alive = check_screen_running()

        if state["action"] == "stopping":
            if not is_alive:
                state["is_running"] = False
                perform_backup()
            continue

        if state["action"] in ["starting", "backing_up"]: 
            if is_alive and os.path.exists(log_path):
                state["log_pos"] = os.path.getsize(log_path)
            continue

        if state["is_running"] and not is_alive:
            state["is_running"] = False
            state["message"] = "⚠️ 偵測到伺服器異常關閉或崩潰，自動啟動備份程序..."
            perform_backup()
            continue

        elif not state["is_running"] and is_alive:
            state["is_running"] = True
            state["message"] = "🟢 伺服器運作中"
            if os.path.exists(log_path):
                state["log_pos"] = os.path.getsize(log_path)

        if state["is_running"] and state["action"] == "idle" and os.path.exists(log_path):
            try:
                current_size = os.path.getsize(log_path)
                if current_size < state["log_pos"]:
                    state["log_pos"] = 0 
                    
                if current_size > state["log_pos"]:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(state["log_pos"])
                        new_lines = f.readlines()
                        state["log_pos"] = f.tell() 
                        
                        for line in new_lines:
                            clean_line = line.strip()
                            if "Server empty for" in clean_line and clean_line.endswith(", pausing"):
                                state["action"] = "stopping"
                                state["message"] = "💤 偵測到伺服器閒置，自動啟動關機與備份..."
                                state["progress"] = 10
                                global server_process
                                if server_process and server_process.poll() is None:
                                    try:
                                        server_process.stdin.write(b'stop\n')
                                        server_process.stdin.flush()
                                    except Exception as e:
                                        print(f"Error stopping server: {e}")
                                break 
            except Exception:
                pass 

def start_task():
    global state, server_process
    state["action"] = "starting"
    state["progress"] = 10
    
    state["message"] = "🧹 正在清理系統環境..."
    # 移除了 Windows 不支援的 screen -wipe 指令

    state["message"] = "🔄 正在執行 Updater 腳本..."
    try:
        updater_dir = os.path.join(JAVA_DIR, 'updater')
        updater_path = os.path.join(updater_dir, 'update.py')
        
        if os.path.exists(updater_path):
            try:
                # 補上 cwd 參數，確保 updater 腳本內部的相對路徑能正常解析
                subprocess.run([sys.executable, 'update.py'], cwd=updater_dir, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                # 擷取腳本實際印出的錯誤訊息以利除錯
                error_output = e.stderr.strip() if e.stderr else str(e)
                raise Exception(f"Updater 腳本執行失敗: {error_output}")
        
        state["progress"] = 30
        state["message"] = "🔍 正在檢查 Java 環境..."
        
        try:
            subprocess.run(['java', '-version'], check=True, capture_output=True)
        except Exception:
            state["message"] = "❌ 啟動失敗：環境變數找不到 Java！(請確認 Flask 執行權限)"
            time.sleep(7)
            state["action"] = "idle"
            state["progress"] = 0
            return

        state["progress"] = 40
        state["message"] = "☕ 正在啟動 Java 伺服器..."
        
        log_path = os.path.join(JAVA_DIR, 'console_output.log')
        log_file = open(log_path, 'a', encoding='utf-8')
        
        server_process = subprocess.Popen(
            [
                'java', 
                '-Xms1G', 
                '-Xmx3G', 
                '-XX:+UseG1GC', 
                '-XX:ParallelGCThreads=2', 
                '-jar', 'server.jar', 
                'nogui'  
            ], 
            cwd=JAVA_DIR, 
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        
        state["progress"] = 80
        state["message"] = "⏳ 正在等待伺服器初始化..."
        
        time.sleep(5) 
        
        if not check_screen_running():
            state["message"] = "❌ 啟動失敗！伺服器瞬間崩潰，請查看 console_output.log"
            time.sleep(5)
            state["action"] = "idle"
            state["progress"] = 0
            return
            
        state["is_running"] = True
        time.sleep(10)
        
        log_path = os.path.join(JAVA_DIR, 'console_output.log')
        if os.path.exists(log_path):
            state["log_pos"] = os.path.getsize(log_path)
        else:
            state["log_pos"] = 0

        state["message"] = "🟢 伺服器運作中"
        state["progress"] = 100
        time.sleep(2)
    except Exception as e:
        state["message"] = f"❌ 啟動發生嚴重錯誤: {str(e)}"
        time.sleep(5)
    finally:
        if state["action"] == "starting":
            state["action"] = "idle"
            state["progress"] = 0

# ================= 路由與登入邏輯 =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 驗證帳號密碼是否正確
        if username in AUTHORIZED_USERS and AUTHORIZED_USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = '帳號或密碼錯誤，請重新輸入！'
            
    return render_template_string(LOGIN_PAGE, error=error)

@app.route('/logout')
def logout():
    session.clear() # 清除通行證
    return redirect(url_for('login'))

@app.route('/')
def index():
    # 檢查有沒有通行證
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template_string(HTML_PAGE)

@app.route('/status', methods=['GET'])
def get_status():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    return jsonify(state)

@app.route('/start', methods=['POST'])
def start_cmd():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    if state["action"] != "idle": return jsonify({"error": "Busy"}), 400
    threading.Thread(target=start_task, daemon=True).start()
    return jsonify({"status": "starting"})

@app.route('/stop', methods=['POST'])
def stop_cmd():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    if state["action"] != "idle": return jsonify({"error": "Busy"}), 400
    state["action"] = "stopping"
    state["progress"] = 10
    state["message"] = "🛑 正在儲存世界並關閉伺服器..."
    global server_process
    if server_process and server_process.poll() is None:
        try:
            server_process.stdin.write(b'stop\n')
            server_process.stdin.flush()
        except:
            pass
    return jsonify({"status": "stopping"})

if __name__ == '__main__':
    threading.Thread(target=server_monitor, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)