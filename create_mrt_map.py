import pandas as pd
import folium
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ==============================
# 讀取資料
# ==============================

INPUT_FILE = "mrt_exits.csv"
OUTPUT_FILE = "mrt_map.html"
VALIDATION_FILE = "mrt_no_escalator_targets.json"

df = pd.read_csv(INPUT_FILE)

df["PositionLon"] = pd.to_numeric(df["PositionLon"], errors="coerce")
df["PositionLat"] = pd.to_numeric(df["PositionLat"], errors="coerce")
df = df.dropna(subset=["PositionLon", "PositionLat"])


# ==============================
# 建立地圖（Esri 街道底圖，灰階效果由 CSS 套用）
# ==============================

m = folium.Map(
    location=[25.0478, 121.5170],
    zoom_start=14,
    max_zoom=19,
    control_scale=True,
    tiles=None
)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="灰階街道地圖",
    overlay=False,
    control=False,
    max_zoom=19,
    max_native_zoom=19
).add_to(m)


# ==============================
# 建立圖層
# ==============================

all_layer = folium.FeatureGroup(
    name="全部捷運出口",
    show=True
)

missing_layer = folium.FeatureGroup(
    name="設施缺失出口",
    show=True
)

station_label_layer = folium.FeatureGroup(
    name="站名標示",
    show=True
)


# ==============================
# 統計數字（動態計算，用於 CMD 驗證輸出）
# ==============================

total_count = 0
no_escalator_only_count = 0
no_elevator_only_count = 0
both_missing_count = 0

seen_stations = set()


# ==============================
# 加入每一個捷運出口
# ==============================

for _, row in df.iterrows():

    station_name = row["StationName"]
    exit_name = row["ExitName"]

    escalator = row["Escalator"]
    elevator = row["Elevator"]
    stair = row["Stair"]

    # --------------------------
    # 判斷邏輯：Escalator 用數值比較，Elevator 用布林值判斷，兩者不可混用
    # --------------------------

    escalator_missing = (not pd.isna(escalator)) and (float(escalator) == 0)
    elevator_missing = (not pd.isna(elevator)) and (bool(elevator) == False)

    if pd.isna(escalator):
        escalator_text = "未知"
    else:
        escalator_text = str(int(escalator))

    elevator_text = "未知" if pd.isna(elevator) else ("有" if bool(elevator) else "無")
    stair_text = "未知" if pd.isna(stair) else ("有" if bool(stair) else "無")

    total_count += 1

    popup_html = f"""
    <div style="font-family: Arial, sans-serif; width: 250px;">
        <h4>{station_name}</h4>
        <b>出口：</b>{exit_name}<br><br>
        <b>電扶梯：</b>{escalator_text}<br>
        <b>電梯：</b>{elevator_text}<br>
        <b>樓梯：</b>{stair_text}<br><br>
        <b>經度：</b>{row["PositionLon"]}<br>
        <b>緯度：</b>{row["PositionLat"]}
    </div>
    """

    # --------------------------
    # 全部出口（背景參考，淺綠色且不加外框）
    # --------------------------

    marker = folium.CircleMarker(
        location=[row["PositionLat"], row["PositionLon"]],
        radius=11,
        popup=folium.Popup(popup_html, max_width=300),
        color="#06C755",
        weight=0,
        fill=True,
        fill_color="#06C755",
        fill_opacity=0.35
    )
    marker.add_to(all_layer)

    # --------------------------
    # 缺失設施出口：靠顏色與尺寸區隔，不加白色外框
    # --------------------------

    if escalator_missing and elevator_missing:
        # 兩者皆缺：深藍色
        both_missing_count += 1
        point_color = "#2E4E8A"
        radius = 11

    elif escalator_missing and not elevator_missing:
        # 僅缺電扶梯：淺藍色
        no_escalator_only_count += 1
        point_color = "#7EA6E0"
        radius = 11

    elif elevator_missing and not escalator_missing:
        # 僅缺電梯：紫色
        no_elevator_only_count += 1
        point_color = "#7B4B94"
        radius = 11

    else:
        point_color = None

    if point_color:
        missing_marker = folium.CircleMarker(
            location=[row["PositionLat"], row["PositionLon"]],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=300),
            color=point_color,
            weight=0,
            fill=True,
            fill_color=point_color,
            fill_opacity=0.95
        )
        missing_marker.add_to(missing_layer)

    # --------------------------
    # 站名標示（每站只標一次）
    # --------------------------

    if station_name not in seen_stations:
        seen_stations.add(station_name)

        folium.map.Marker(
            [row["PositionLat"], row["PositionLon"]],
            icon=folium.DivIcon(
                icon_size=(150, 20),
                icon_anchor=(0, 0),
                html=f'<div style="font-size:12px; font-weight:bold; color:#1F3864; text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;">{station_name}</div>'
            )
        ).add_to(station_label_layer)


# ==============================
# 加入圖層到地圖
# ==============================

all_layer.add_to(m)
missing_layer.add_to(m)
station_label_layer.add_to(m)


# ==============================
# 加入圖層控制器
# ==============================

folium.LayerControl(
    collapsed=False
).add_to(m)


# ==============================
# 標題
# ==============================

title_html = """
<div style="
position: fixed;
top: 10px;
left: 50px;
z-index: 9999;
background-color: white;
padding: 10px 15px;
border: 2px solid #1F3864;
border-radius: 5px;
font-size: 18px;
font-weight: bold;
color: #1F3864;
">
臺北捷運出入口設施分布
</div>
"""

# ==============================
# 圖例（四色配置，靠顏色與圓點大小示意）
# ==============================

legend_html = """
<div style="
position: fixed;
bottom: 30px;
left: 10px;
z-index: 9999;
background-color: white;
padding: 12px 15px;
border: 2px solid #1F3864;
border-radius: 5px;
font-size: 14px;
line-height: 1.9;
">
<b style="color:#1F3864;">圖例</b><br>
<span style="color:#06C755; font-size:18px;">●</span> 出口<br>
<span style="color:#7EA6E0; font-size:18px;">●</span> 缺電扶梯<br>
<span style="color:#7B4B94; font-size:18px;">●</span> 缺電梯<br>
<span style="color:#2E4E8A; font-size:18px;">●</span> 電扶梯／電梯皆缺
</div>
"""

m.get_root().html.add_child(folium.Element(title_html))
m.get_root().html.add_child(folium.Element(legend_html))

# 將底圖圖磚轉成灰階，不影響上方的彩色圓點與標示
grayscale_css = """
<style>
.leaflet-tile-pane {
    filter: grayscale(100%);
}
</style>
"""
m.get_root().html.add_child(folium.Element(grayscale_css))


# ==============================
# 輸出地圖
# ==============================

m.save(OUTPUT_FILE)


# ==============================
# 驗證：對照 mrt_no_escalator_targets.json 的數量
# ==============================

validation_note = "（找不到 mrt_no_escalator_targets.json，略過自動驗證，請自行比對）"

if os.path.exists(VALIDATION_FILE):
    with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
        target_data = json.load(f)

    if isinstance(target_data, list):
        target_count = len(target_data)
    elif isinstance(target_data, dict):
        target_count = len(target_data)
    else:
        target_count = None

    if target_count is not None:
        escalator_missing_count = no_escalator_only_count + both_missing_count
        if target_count == escalator_missing_count:
            validation_note = f"✅ 驗證通過：json 筆數（{target_count}）與程式算出的「缺少電扶梯」（{escalator_missing_count}）一致"
        else:
            validation_note = (
                f"⚠️ 驗證不一致：json 筆數為 {target_count}，"
                f"但程式算出的「缺少電扶梯」（僅缺電扶梯＋兩者皆缺）為 {escalator_missing_count}，"
                f"請檢查 json 檔案定義的條件是否跟本程式一致"
            )


print("===================================")
print("地圖建立完成！")
print(f"資料筆數：{total_count}")
print(f"缺電扶梯：{no_escalator_only_count}")
print(f"缺電梯：{no_elevator_only_count}")
print(f"兩者皆缺：{both_missing_count}")
print(f"輸出檔案：{OUTPUT_FILE}")
print("-----------------------------------")
print(validation_note)
print("===================================")
print("提示：城市尺度截圖前，記得手動關閉「站名標示」圖層勾選。")