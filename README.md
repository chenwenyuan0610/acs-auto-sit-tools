# HiTRUST ACS Cloud Auto SIT Tools

模擬 ACS 自動化測試交易工具，用於執行 3-D Secure Browser ACS SIT 案例，包含 AReq、ARes、CReq、CRes、OTP Challenge 與交易結果比對。

本工具為本機 Web 應用程式：Python 負責啟動後端與提供前端頁面，使用者透過瀏覽器操作，不需要另外安裝前端套件。

## 功能摘要

- 執行 Browser ACS SIT 測試案例。
- 支援 OTP、驗證方式選擇與 OOB 等發卡行模式。
- 逐筆執行案例，預設每筆間隔 3 秒。
- 每完成一筆即更新案例狀態與執行統計。
- 失敗案例可單獨重新執行，其他案例結果會保留。
- 手動切換至「測試結果」查看完整結果。
- 支援保存測試結果與下載 HTML 報告。
- 支援匯入發卡行 wording Excel 設定。

## 環境需求

- Python 3.12 或以上版本。
- Chrome、Microsoft Edge 或其他現代瀏覽器。
- 可連線至測試環境的 ACS、OTP 查詢與交易結果查詢 API。
- Windows 建議使用 PowerShell 執行以下指令。

確認 Python 版本：

```powershell
python --version
```

如果系統找不到 `python`，請先安裝 Python 3.12+，並在安裝時勾選 **Add Python to PATH**。

## 取得專案

可以透過 Git clone，或直接取得專案 ZIP 後解壓縮。

使用 PowerShell 進入專案資料夾：

```powershell
cd "C:\path\to\acs-auto-sit-tools"
```

後續所有指令都必須在包含 `pyproject.toml` 與 `README.md` 的專案根目錄執行。

## 第一次安裝

建議使用 Python 虛擬環境，避免影響電腦上的其他 Python 專案。

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

如果 PowerShell 阻擋虛擬環境啟用，可只針對目前視窗調整：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

安裝完成後，之後重新開啟終端機只需要再次啟用 `.venv`，不必重複安裝套件。

## 啟動工具

在專案根目錄執行：

```powershell
python -m acs_auto_sit --host 127.0.0.1 --port 8000
```

看到以下訊息代表啟動成功：

```text
ACS Auto SIT running at http://127.0.0.1:8000/
```

接著使用瀏覽器開啟：

<http://127.0.0.1:8000/>

啟動工具的 PowerShell 視窗必須保持開啟。按 `Ctrl + C` 可停止服務。

### 每次重新開啟專案

Windows：

```powershell
cd "C:\path\to\acs-auto-sit-tools"
.\.venv\Scripts\Activate.ps1
python -m acs_auto_sit --host 127.0.0.1 --port 8000
```

## 首次使用設定

開啟頁面後，先點選「前往設定」，確認本次測試需要的設定：

1. 選擇發卡行設定與發卡行模式。
2. 選擇 Challenge 偏好與語系。
3. 填入正確的 ACS AReq URL。
4. 填入本次測試使用的有效卡號與無效卡號。
5. 確認 OTP 來源模式、成功 OTP、失敗 OTP 與錯誤次數上限。
6. 確認 OTP 查詢 URL 與交易結果查詢 URL。
7. 視需要調整案例間隔秒數；預設為 3 秒。

設定與測試卡號會保存於目前瀏覽器的 `localStorage`，重新整理或重新開啟頁面後不需要重新輸入。請只使用測試資料，不要輸入真實持卡人卡號或正式環境機密。

## 執行測試案例

1. 進入「執行案例」。
2. 勾選需要執行的案例，或點選「全部執行」。
3. 點選「執行選取案例」。
4. 工具會逐筆執行，並在每筆完成後更新狀態與統計。
5. 全部執行完成後仍會停留在案例頁。
6. 若有失敗案例，可以只勾選失敗案例重新執行。
7. 重跑完成後，只會更新該案例；同一頁面工作階段內的其他結果會保留。
8. 確認案例皆完成後，手動點選右上角「測試結果」。

執行結果只會在目前頁面工作階段內累積。重新整理瀏覽器後，未保存的累積結果會清空。

## 保存與匯出結果

在「測試結果」頁可以：

- 查看成功、失敗、略過與錯誤數量。
- 查看各 Case 的 ACS Transaction ID、交易結果與耗時。
- 保存已完成的測試結果。
- 下載 HTML 測試報告。

保存的測試結果以 JSON 檔案存放於：

```text
data/sit-runs/
```

此專案目前沒有使用資料庫。瀏覽器設定存放於 `localStorage`，手動保存的執行結果則存放於上述本機資料夾。

## 使用命令列執行案例（選用）

請先啟動本機 Web 服務，再開啟另一個已啟用 `.venv` 的 PowerShell 視窗。

執行指定案例：

```powershell
python tools\run_live_sit.py --cases case01,case03,case09 --output live_run_result.json
```

執行全部 Browser 案例：

```powershell
python tools\run_live_sit.py --output live_run_result.json
```

常用參數：

```text
--server                 本機工具網址，預設 http://127.0.0.1:8000
--cases                  以逗號分隔的 Case ID；未提供時執行全部案例
--output                 JSON 結果檔名
--timeout-seconds        單筆請求逾時秒數
--issuer-mode            發卡行模式
--preferred-challenge    Challenge 偏好
--otp-source-mode        customer_generated 或 acs_generated
--case-delay-seconds     案例間隔秒數
```

命令列工具會使用 `static/index.html` 中的預設交易設定，不會讀取瀏覽器 `localStorage` 內的設定。正式執行前請確認預設 ACS URL、卡號與 OTP 設定符合測試需求。

## 分享給區網內其他同事使用

最安全且最簡單的方式，是讓每位同事在自己的電腦上依照前述步驟啟動。

如果要讓同一區網內的同事連線到你的電腦，可改用：

```powershell
python -m acs_auto_sit --host 0.0.0.0 --port 8000
```

查詢 Windows 電腦的 IPv4 位址：

```powershell
ipconfig
```

同事使用以下網址連線：

```text
http://你的IPv4位址:8000/
```

例如：`http://192.168.1.20:8000/`。

Windows 防火牆可能會詢問是否允許 Python 通過私人網路。此工具沒有登入與權限控管，請只在可信任的測試網路使用，不要直接開放至網際網路。

## 常見問題

### 瀏覽器顯示 `ERR_CONNECTION_REFUSED`

通常表示本機服務沒有啟動、已停止，或網址與 Port 不一致。

1. 確認執行服務的 PowerShell 視窗仍保持開啟。
2. 確認終端機有顯示 `ACS Auto SIT running at ...`。
3. 確認瀏覽器網址為 <http://127.0.0.1:8000/>。
4. 回到專案根目錄重新執行啟動指令。
5. 確認 8000 Port 是否可連線：

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
```

### 8000 Port 已被占用

改用其他 Port：

```powershell
python -m acs_auto_sit --host 127.0.0.1 --port 8001
```

然後開啟 <http://127.0.0.1:8001/>。

查看占用 8000 Port 的程序：

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

### 找不到 `acs_auto_sit` 模組

請確認：

- 目前位於專案根目錄。
- 已啟用 `.venv`。
- 已執行 `python -m pip install -e .`。
- `python` 與 `pip` 使用同一個虛擬環境。

可執行以下指令確認：

```powershell
python -c "import acs_auto_sit; print(acs_auto_sit.__file__)"
```

### 頁面仍顯示舊版內容

按 `Ctrl + F5` 強制重新載入。如果仍未更新，停止服務後重新啟動。

### ACS、OTP 或交易結果查詢失敗

請確認：

- 電腦已連上正確的公司網路或 VPN。
- 測試環境 URL 正確。
- Proxy、防火牆與憑證政策允許連線到目標服務。
- 測試卡號、OTP 來源模式與發卡行模式正確。
- 不同案例之間保留足夠間隔，預設建議 3 秒。

## 執行測試（開發者）

先安裝 pytest：

```powershell
python -m pip install pytest
```

執行完整測試：

```powershell
python -m pytest
```

## 專案結構

```text
acs_auto_sit/   Python 後端、ACS 流程與結果比對邏輯
static/         Web 操作介面
sit_cases/      SIT 案例定義
data/           案例進度、wording 與已保存結果
tools/          命令列輔助工具
tests/          自動化測試
pyproject.toml  Python 版本與相依套件設定
```

## 安全提醒

- 本工具僅供 SIT／測試環境使用。
- 請勿使用正式卡號、正式 OTP、正式環境憑證或其他敏感資料。
- 對外分享專案前，請確認 `data/sit-runs/`、報告、Log 與本機測試輸出未包含敏感資料。
- 若使用 `--host 0.0.0.0`，請限制在可信任的內部測試網路。
