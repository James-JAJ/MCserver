# 🌟 Minecraft 全自動伺服器控制面板與備份系統

這是一個基於 Python (Flask) 打造的現代化 Minecraft 伺服器後端專案。它大幅簡化了伺服器的啟動、關閉與維護，並提供了網頁版視覺化的管理介面。非常適合希望將伺服器運作自動化，或是開放給朋友遊玩與觀看的創作者！

## ✨ 主要功能 (Features)

1. **🌐 網頁版控制面板 (Web UI)**
   - 透過瀏覽器即可監控與操作伺服器。
   - 支援即時狀態顯示與前端進度條（開機、關機、備份進度）。
2. **🔒 安全驗證登入 (Secure Access)**
   - 內建通行證 (Session) 機制與帳號密碼登入確認，避免外人隨意操控。
3. **☁️ 雲端自動化備份 (Cloud Backup)**
   - 關機或伺服器崩潰時，世界檔案 (`world` 資料夾) 會自動打包壓縮。
   - 自動上傳至 Dropbox 雲端空間（支援大檔案分塊上傳），並自動刪除超出保留數量的舊備份。
4. **💤 智能掛機偵測 (Idle Detection)**
   - 系統會透過 `console_output.log` 定期監測伺服器日誌，若發現玩家全部離線閒置，將自動執行**安全關機並觸發備份**，節省主機資源！
5. **🔄 自動更新聯動 (Auto Updater)**
   - 啟動伺服器前，會自動執行 `updater/update.py` 檢查各種模組或核心的更新，確保遊戲環境永遠在最新狀態。

---

## 🛠️ 如何修改為您自己的專屬版本？

如果您想借用這套系統，套用在您自己的 Minecraft 伺服器上，請打開 `web_panel.py` 並依照以下步驟修改：

### 1. 修改網頁登入與安全設定 (約第 18~24 行)
確保控制面板不會停留在預設密碼，保障您的伺服器安全：
```python
# 必須修改成一段只有您知道的亂碼字串，確保網頁 Session 安全
app.secret_key = '請將這裡改成您的隨機密碼文字' 

# 在這裡設定允許登入的帳號與密碼 (格式: {"帳號": "密碼"})
AUTHORIZED_USERS = {
    "admin": "YOUR_SECURE_PASSWORD",    # 修改成您自己的密碼
    "您的好友": "好友密碼"                # 您可以隨意新增多組帳號
}
```

### 2. 設定 Dropbox 雲端備份金鑰 (約第 28~31 行)
如果要啟用自動備份上傳功能，必須前往 [Dropbox App Console](https://www.dropbox.com/developers/apps) 建立應用程式並將憑證填入：
```python
DROPBOX_APP_KEY = 'YOUR_DROPBOX_APP_KEY'        
DROPBOX_APP_SECRET = 'YOUR_DROPBOX_APP_SECRET'     
DROPBOX_REFRESH_TOKEN = 'YOUR_DROPBOX_REFRESH_TOKEN' 
```
> **提示**：系統預設會保留最近的 7 個備份。您可以透過修改緊接在下面的 `MAX_BACKUPS = 7` (第 32 行) 變數來調整最大保留數量。

### 3. 客製化記憶體與啟動核心 (約第 381~390 行)
如果您使用的是不同的伺服器核心（例如: Paper, Fabric, Forge）或是需要為伺服器分配更多記憶體，請往下找到 `start_task` 函數，修改 `subprocess.Popen` 裡的指令設定：
```python
server_process = subprocess.Popen(
    [
        'java', 
        '-Xms1G',              # 伺服器最小記憶體，例如改成 -Xms4G
        '-Xmx3G',              # 伺服器最大記憶體，例如改成 -Xmx4G
        '-XX:+UseG1GC', 
        '-XX:ParallelGCThreads=2', 
        '-jar', 'server.jar',  # 如果您的檔案名稱叫 paper.jar 或 forge.jar，請在此處替換
        'nogui'  
    ], 
...
```

### 4. 撰寫專屬 Updater 邏輯
專案在開機前預設會執行 `updater/update.py`。您可以根據需求，在該檔案中撰寫您的「伺服器啟動前置作業」（例如：從遠端下載最新的 Mods 或同步設定檔）。
*如果您不需要自動更新器，可以暫時將 `web_panel.py` 中執行 Updater（約第 349~361 行）的程式碼註解掉。*

---

## 🚀 執行與使用方式

1. 確保電腦主機已安裝 **Python 3.x** 及 **Java**，並安裝相關套件：
   ```bash
   pip install flask dropbox
   ```
2. 將您的 Minecraft 伺服器執行檔放置於此專案根目錄（預設請命名為 `server.jar`，或改名後依照步驟 3 去改 Python 程式碼）。
3. 執行網頁面板主程式：
   ```bash
   python web_panel.py
   ```
4. 開啟瀏覽器訪問 `http://localhost:8080` (或對應的主機 IP 取代 localhost) 即可開啟面板首頁！
