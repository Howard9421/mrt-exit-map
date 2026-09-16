import pandas as pd
import folium
import json
import os
import sys
import html
import math

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
# 產生站內出口設施示意圖（新增功能）
# ==============================

def diagram_value(value, value_type):
    """將資料欄位轉為示意圖使用的有、無或未知文字。"""
    if pd.isna(value):
        return "未知"
    if value_type == "escalator":
        try:
            return "無" if float(value) == 0 else "有"
        except (TypeError, ValueError):
            return "未知"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "有"):
            return "有"
        if normalized in ("false", "0", "no", "無"):
            return "無"
        return "未知"
    return "有" if bool(value) else "無"


def diagram_status_color(exit_rows):
    """依現有缺失設施配色邏輯決定單一出口顏色。"""
    escalator = diagram_value(exit_rows["Escalator"], "escalator")
    elevator = diagram_value(exit_rows["Elevator"], "elevator")
    if escalator == "無":
        return "#2E4E8A"
    if elevator == "無":
        return "#7B4B94"
    if escalator == "有" and elevator == "有":
        return "#06C755"
    return "#808080"


def diagram_icon(value, icon):
    symbol = "✓" if value == "有" else ("✗" if value == "無" else "?")
    return f'<span class="facility {value}">{symbol}</span>'


def build_station_diagrams(station_df):
    """依站名建立嵌入 popup 的放射圖或清單圖，不輸出獨立檔案。"""
    station_diagrams = {}
    station_search_data = {}

    for station_name, station_rows in station_df.groupby("StationName", sort=True):
        station_name = str(station_name)
        station_rows = station_rows.drop_duplicates(subset=["ExitName"])
        station_search_data[station_name] = {
            "lat": float(station_rows["PositionLat"].mean()),
            "lon": float(station_rows["PositionLon"].mean())
        }

        exits = []
        for _, exit_row in station_rows.iterrows():
            exits.append({
                "name": "未知" if pd.isna(exit_row["ExitName"]) else str(exit_row["ExitName"]),
                "escalator": diagram_value(exit_row["Escalator"], "escalator"),
                "elevator": diagram_value(exit_row["Elevator"], "elevator"),
                "stair": diagram_value(exit_row["Stair"], "stair"),
                "color": diagram_status_color(exit_row)
            })

        escaped_station = html.escape(station_name)
        if len(exits) > 8:
            exit_markup = "".join(
                f"""
                <tr>
                    <td>{html.escape(exit_data["name"])}</td>
                    <td>{diagram_icon(exit_data["elevator"], "")}</td>
                    <td>{diagram_icon(exit_data["escalator"], "")}</td>
                    <td>{diagram_icon(exit_data["stair"], "")}</td>
                </tr>
                """
                for exit_data in exits
            )
            content = f"""
            <table class="exit-list">
                <thead><tr><th>出口</th><th>電梯</th><th>手扶梯</th><th>樓梯</th></tr></thead>
                <tbody>{exit_markup}</tbody>
            </table>
            """
        else:
            node_radius = 32 + max(0, len(exits) - 6) * 2
            orbit_x = 270 + max(0, len(exits) - 6) * 35
            orbit_y = 210 + max(0, len(exits) - 6) * 28
            center_x, center_y = orbit_x + 150, orbit_y + 120
            view_width = (center_x + orbit_x + 150)
            view_height = (center_y + orbit_y + 120)
            svg_lines = []
            for index, exit_data in enumerate(exits):
                angle = (2 * math.pi * index / len(exits)) - math.pi / 2
                x = center_x + orbit_x * math.cos(angle)
                y = center_y + orbit_y * math.sin(angle)
                line_label_x = (center_x + x) / 2
                line_label_y = (center_y + y) / 2
                svg_lines.append(
                    f"""
                    <line x1="{center_x}" y1="{center_y}" x2="{x:.1f}" y2="{y:.1f}"
                        stroke="{exit_data["color"]}" stroke-width="3"/>
                    <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_radius}"
                        fill="{exit_data["color"]}" opacity="0.95"/>
                    <text x="{line_label_x:.1f}" y="{line_label_y:.1f}"
                        class="exit-name">{html.escape(exit_data["name"])}</text>
                    <text x="{x:.1f}" y="{y - 5:.1f}" class="exit-icon">
                        電梯{exit_data["elevator"]} 手扶梯{exit_data["escalator"]}
                    </text>
                    <text x="{x:.1f}" y="{y + 17:.1f}" class="exit-icon">
                        樓梯{exit_data["stair"]}
                    </text>
                    """
                )
            content = f"""
            <svg class="radial" viewBox="0 0 {view_width:.1f} {view_height:.1f}" role="img"
                aria-label="{escaped_station}站出口設施放射圖">
                {''.join(svg_lines)}
                <circle cx="{center_x}" cy="{center_y}" r="65" fill="#1F3864"/>
                <text x="{center_x}" y="{center_y + 6}" class="center-label">月台／大廳</text>
            </svg>
            """

        diagram_html = f"""
        <section class="station-diagram">
        {content}
        </section>
        """
        station_diagrams[station_name] = diagram_html

    return station_diagrams, station_search_data

station_diagrams, station_search_data = build_station_diagrams(df)


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
station_marker_names = {}


# ==============================
# 加入每一個捷運出口
# ==============================

for _, row in df.iterrows():

    station_name = row["StationName"]
    exit_name = row["ExitName"]
    station_key = html.escape(str(station_name), quote=True)

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
    <div style="font-family: 'Noto Sans TC', 'Microsoft JhengHei', Arial, sans-serif; line-height: 1.6; letter-spacing: 0.02em; width: 250px; padding: 12px;">
        <div style="font-size: 17px;">
            <b>出口：</b>{exit_name}<br>
            <b>電扶梯：</b>{escalator_text}<br>
            <b>電梯：</b>{elevator_text}<br>
            <b>樓梯：</b>{stair_text}<br><br>
        </div>
        <button type="button" class="station-diagram-button"
            data-station="{station_key}"
            onclick="toggleStationDiagram(this)">出口示意圖</button>
        <div class="station-diagram-container" data-diagram-station="{station_key}"></div>
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
    station_marker_names.setdefault(str(station_name), marker.get_name())

    # --------------------------
    # 缺失設施出口：靠顏色與尺寸區隔，不加白色外框
    # --------------------------

    if escalator_missing and elevator_missing:
        # 兩者皆缺：預設以深藍色顯示
        both_missing_count += 1
        point_color = "#2E4E8A"
        marker_class = "mrt-both-missing"
        radius = 11

    elif escalator_missing and not elevator_missing:
        # 僅缺手扶梯：深藍色
        no_escalator_only_count += 1
        point_color = "#2E4E8A"
        marker_class = "mrt-escalator-missing"
        radius = 11

    elif elevator_missing and not escalator_missing:
        # 僅缺電梯：紫色
        no_elevator_only_count += 1
        point_color = "#7B4B94"
        marker_class = "mrt-elevator-missing"
        radius = 11

    else:
        point_color = None
        marker_class = None

    if point_color:
        missing_marker = folium.CircleMarker(
            location=[row["PositionLat"], row["PositionLon"]],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=300),
            color=point_color,
            weight=0,
            fill=True,
            fill_color=point_color,
            fill_opacity=0.95,
            class_name=marker_class
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
<label><input type="checkbox" checked data-mrt-toggle="escalator" onchange="toggleMrtMarkers()"> <span style="color:#2E4E8A; font-size:18px;">●</span> 缺手扶梯</label><br>
<label><input type="checkbox" checked data-mrt-toggle="elevator" onchange="toggleMrtMarkers()"> <span style="color:#7B4B94; font-size:18px;">●</span> 缺電梯</label><br>
<label><input type="checkbox" checked data-mrt-toggle="both" onchange="toggleMrtMarkers()"> <span style="color:#7EA6E0; font-size:18px;">●</span> 手扶梯／電梯皆缺</label>
</div>
<script>
function toggleMrtMarkers() {
    var toggles = document.querySelectorAll("[data-mrt-toggle]");
    var enabled = {};
    toggles.forEach(function (toggle) {
        enabled[toggle.dataset.mrtToggle] = toggle.checked;
    });
    document.querySelectorAll(".leaflet-overlay-pane path").forEach(function (path) {
        var classes = path.getAttribute("class") || "";
        var category = classes.indexOf("mrt-escalator-missing") >= 0
            ? "escalator"
            : classes.indexOf("mrt-elevator-missing") >= 0
                ? "elevator"
                : classes.indexOf("mrt-both-missing") >= 0
                    ? "both"
                    : null;
        if (!category) {
            return;
        }
        var visible = category === "both"
            ? enabled.both || enabled.escalator || enabled.elevator
            : enabled[category];
        if (!visible) {
            path.style.display = "none";
            return;
        }
        path.style.display = "";
        if (category === "both") {
            var bothColor = enabled.both
                ? "#7EA6E0"
                : enabled.escalator
                    ? "#2E4E8A"
                    : "#7B4B94";
            path.style.fill = bothColor;
            path.style.stroke = bothColor;
        }
    });
}
window.addEventListener("load", toggleMrtMarkers);
</script>
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

# 站內示意圖與站名搜尋（新增功能，不影響既有圖層與圖例）
station_diagrams_json = json.dumps(
    station_diagrams, ensure_ascii=False
).replace("</", "<\\/")
station_search_json = json.dumps(
    {
        name: {
            "lat": data["lat"],
            "lon": data["lon"],
            "marker": station_marker_names.get(name)
        }
        for name, data in station_search_data.items()
    },
    ensure_ascii=False
).replace("</", "<\\/")
station_diagram_ui = f"""
<style>
.station-diagram-button {{
    background: #1F3864; color: white; border: 0; border-radius: 4px;
    padding: 6px 10px; cursor: pointer; font-family: Arial, "Microsoft JhengHei", sans-serif;
}}
.station-diagram-button:hover {{ background: #2E4E8A; }}
.station-diagram-container {{ display: none; margin-top: 8px; max-height: 360px; overflow: auto; }}
.station-diagram {{ color: #1F3864; font-family: Arial, "Microsoft JhengHei", sans-serif; }}
.station-diagram, .station-diagram button, .station-diagram table {{
    font-family: "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif;
    line-height: 1.6; letter-spacing: 0.02em;
}}
.station-diagram h4 {{ margin: 8px 0; font-size: 15px; }}
.diagram-legend {{ margin: 4px 0 8px; color: #666; font-size: 11px; }}
.diagram-legend .complete {{ color: #06C755; }}
.diagram-legend .escalator-missing {{ color: #2E4E8A; }}
.diagram-legend .elevator-missing {{ color: #7B4B94; }}
.radial {{ width: 100%; height: auto; }}
.center-label {{ fill: white; font-size: 18px; text-anchor: middle; }}
.exit-name {{ fill: #1F3864; font-size: 14px; text-anchor: middle; }}
.exit-icon {{ fill: white; font-size: 16px; text-anchor: middle; }}
.exit-list {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
.exit-list th, .exit-list td {{ border-bottom: 1px solid #ddd; padding: 5px; text-align: left; }}
.facility {{ white-space: nowrap; }}
. {{ color: #1E8E3E; background: #e8f8ee; border: 1px solid #1E8E3E; padding: 1px 6px; border-radius: 3px; font-weight: bold; }}
. {{ color: #D93025; background: #fdeceb; border: 1px solid #D93025; padding: 1px 6px; border-radius: 3px; font-weight: bold; }}
.未知 {{ color: #555; background: #f0f0f0; border: 1px solid #999; padding: 1px 4px; border-radius: 3px; }}
.station-search-control {{
    position: fixed; top: 65px; left: 50px; z-index: 9999; width: 230px;
    background: white; border: 2px solid #1F3864; border-radius: 5px; padding: 8px;
    box-shadow: 0 1px 5px #0003;
    font-family: "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif;
    line-height: 1.6; letter-spacing: 0.02em;
}}
.station-search-control input {{
    width: 100%; box-sizing: border-box; padding: 6px 8px;
    border: 1px solid #1F3864; border-radius: 3px; color: #1F3864;
}}
</style>
<div class="station-search-control">
    <input id="station-search" type="search" list="station-options"
        placeholder="搜尋站名" aria-label="搜尋站名">
    <datalist id="station-options"></datalist>
</div>
<script>
var stationDiagrams = {station_diagrams_json};
var stationSearchData = {station_search_json};
function toggleStationDiagram(button) {{
    var stationName = button.getAttribute("data-station");
    var container = button.parentElement.querySelector(".station-diagram-container");
    if (container.style.display === "block") {{
        container.style.display = "none";
        button.textContent = "出口示意圖";
        var map = {m.get_name()};
        if (map && map._popup) {{
            map._popup.update();
        }}
        return;
    }}
    container.innerHTML = stationDiagrams[stationName] || "<p>找不到本站示意圖。</p>";
    container.style.display = "block";
    button.textContent = "較少";
    var map = {m.get_name()};
    if (map && map._popup) {{
        map._popup.update();
    }}
}}
function openStationFromSearch() {{
    var input = document.getElementById("station-search");
    var stationName = input.value.trim();
    var station = stationSearchData[stationName];
    if (!station) return;
    var map = {m.get_name()};
    map.flyTo([station.lat, station.lon], 16);
    var marker = window[station.marker];
    if (marker) {{
        marker.openPopup();
        setTimeout(function () {{
            var button = document.querySelector(".leaflet-popup-content .station-diagram-button");
            if (button) {{
                var container = button.parentElement.querySelector(".station-diagram-container");
                if (!container || container.style.display !== "block") {{
                    toggleStationDiagram(button);
                }}
            }}
        }}, 350);
    }}
}}
document.addEventListener("DOMContentLoaded", function () {{
    var datalist = document.getElementById("station-options");
    Object.keys(stationSearchData).sort().forEach(function (name) {{
        var option = document.createElement("option");
        option.value = name;
        datalist.appendChild(option);
    }});
    document.getElementById("station-search").addEventListener("change", openStationFromSearch);
    document.getElementById("station-search").addEventListener("keydown", function (event) {{
        if (event.key === "Enter") openStationFromSearch();
    }});
}});
</script>
"""
m.get_root().html.add_child(folium.Element(station_diagram_ui))


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
            validation_note = f"✅ 驗證通過：json 筆數（{target_count}）與程式算出的「缺少手扶梯」（{escalator_missing_count}）一致"
        else:
            validation_note = (
                f"⚠️ 驗證不一致：json 筆數為 {target_count}，"
                f"但程式算出的「缺少手扶梯」（僅缺手扶梯＋兩者皆缺）為 {escalator_missing_count}，"
                f"請檢查 json 檔案定義的條件是否跟本程式一致"
            )


print("===================================")
print("地圖建立完成！")
print(f"資料筆數：{total_count}")
print(f"缺手扶梯：{no_escalator_only_count}")
print(f"缺電梯：{no_elevator_only_count}")
print(f"兩者皆缺：{both_missing_count}")
print(f"輸出檔案：{OUTPUT_FILE}")
print("-----------------------------------")
print(validation_note)
print("===================================")
print("提示：城市尺度截圖前，記得手動關閉「站名標示」圖層勾選。")