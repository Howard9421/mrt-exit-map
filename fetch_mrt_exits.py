"""
fetch_mrt_exits.py
抓取並清洗「臺北捷運出入口與無障礙/電扶梯設施資料」(TDX API)
供前端組員做地圖化渲染使用。

⚠️ 安全性提醒:
本腳本因應開發環境憑證問題使用 verify=False 略過 SSL 驗證。
正式環境建議改用 `pip install --upgrade certifi` 或設定 REQUESTS_CA_BUNDLE
環境變數來修正憑證鏈,而非永久停用驗證,以避免中間人攻擊風險。
"""

import json
import sys

import pandas as pd
import requests
import urllib3

# 停用 SSL 未驗證警告訊息（因 verify=False 而產生）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============ 請在此處填入您的 TDX API 金鑰 ============
APP_ID = 'b1226026-57beac3f-9453-444c'      
APP_KEY = '3257a54a-0b90-4fd3-a81a-e426527c7871'     # <-- 填入您的 Client Secret
# =======================================================

AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
DATA_URL = "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/StationExit/TRTC?$format=JSON"

CSV_OUTPUT_PATH = "mrt_exits.csv"
JSON_OUTPUT_PATH = "mrt_no_escalator_targets.json"


def get_access_token(app_id: str, app_key: str) -> str:
    """
    使用 Client Credentials 流程向 TDX 取得 Access Token。
    採用乾淨的例外處理，避免未定義變數的問題。
    """
    headers = {"content-type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": app_id,
        "client_secret": app_key,
    }

    try:
        response = requests.post(
            AUTH_URL,
            headers=headers,
            data=data,
            verify=False,  # 開發環境略過憑證驗證
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[錯誤] 無法取得 Access Token: {e}", file=sys.stderr)
        sys.exit(1)

    token_json = response.json()
    access_token = token_json.get("access_token")

    if not access_token:
        print(f"[錯誤] 回應中未包含 access_token: {token_json}", file=sys.stderr)
        sys.exit(1)

    return access_token


def fetch_station_exit_data(access_token: str) -> list:
    headers = {
        "authorization": f"Bearer {access_token}",
        "Accept-Encoding": "gzip",
    }

    try:
        response = requests.get(
            DATA_URL,
            headers=headers,
            verify=False,
            timeout=15,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[錯誤] 無法取得捷運出入口資料: {e}", file=sys.stderr)
        sys.exit(1)

    data = response.json()

    print("\n========== API 原始資料 ==========")
    print(type(data))
    print("資料筆數：", len(data) if isinstance(data, list) else "不是 list")
    
    if isinstance(data, list) and len(data) > 0:
        print("\n第一筆資料：")
        print(json.dumps(data[0], indent=4, ensure_ascii=False))
    else:
        print("\nAPI 回傳內容：")
        print(json.dumps(data, indent=4, ensure_ascii=False))

    print("===================================\n")

    return data


def clean_data(raw_data: list) -> pd.DataFrame:
    """
    將 TDX StationExit API 回傳資料清洗成前端需要的格式。
    TDX API 每一筆資料本身就是一個捷運出入口。
    """

    records = []

    for exit_info in raw_data:
        station_name_obj = exit_info.get("StationName", {}) or {}
        exit_name_obj = exit_info.get("ExitName", {}) or {}
        position = exit_info.get("ExitPosition", {}) or {}

        record = {
            "StationID": exit_info.get("StationID"),
            "StationName": station_name_obj.get("Zh_tw"),
            "ExitID": exit_info.get("ExitID"),
            "ExitName": exit_name_obj.get("Zh_tw"),
            "PositionLon": position.get("PositionLon"),
            "PositionLat": position.get("PositionLat"),
            "Stair": exit_info.get("Stair"),
            "Escalator": exit_info.get("Escalator"),
            "Elevator": exit_info.get("Elevator"),
        }

        records.append(record)

    df = pd.DataFrame(records)

    # 確保經緯度為數值
    for col in ["PositionLon", "PositionLat"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def export_results(df: pd.DataFrame) -> None:
    """
    將清洗後資料匯出為 CSV（UTF-8 BOM）與 JSON（無電扶梯出入口清單）。
    """
    df.to_csv(CSV_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"已匯出 CSV: {CSV_OUTPUT_PATH}（共 {len(df)} 筆資料）")

    if "Escalator" in df.columns:
        no_escalator_df = df[df["Escalator"] == 0]
    else:
        no_escalator_df = df.iloc[0:0]

    no_escalator_records = no_escalator_df.to_dict(orient="records")

    with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(no_escalator_records, f, indent=4, ensure_ascii=False)

    print(f"已匯出 JSON: {JSON_OUTPUT_PATH}（共 {len(no_escalator_records)} 筆無電扶梯出入口）")


def main():
    if not APP_ID or not APP_KEY:
        print("[錯誤] 請先於程式頂端填入 APP_ID 與 APP_KEY。", file=sys.stderr)
        sys.exit(1)

    print("正在取得 Access Token...")
    access_token = get_access_token(APP_ID, APP_KEY)

    print("正在抓取捷運出入口資料...")
    raw_data = fetch_station_exit_data(access_token)

    print("正在清洗資料...")
    df = clean_data(raw_data)

    print("正在匯出結果...")
    export_results(df)

    print("完成！")


if __name__ == "__main__":
    main()